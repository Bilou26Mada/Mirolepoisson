"""
OASIS Agent Profile生成器
将Zep图谱中的实体转换为OASIS模拟平台所需的Agent Profile格式

优化改进：
1. 调用Zep检索功能二次丰富节点信息
2. 优化提示词生成非常详细的人设
3. 区分个人实体和抽象群体实体
"""

import json
import random
import time
import csv
import concurrent.futures
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from openai import OpenAI
from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader

logger = get_logger('mirofish.oasis_profile')


@dataclass
class OasisAgentProfile:
    """OASIS Agent Profile数据结构"""
    # 通用字段
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str
    
    # 可选字段 - Reddit风格
    karma: int = 1000
    
    # 可选字段 - Twitter风格
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500
    
    # 额外人设信息
    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)
    
    # 来源实体信息
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    def to_reddit_format(self) -> Dict[str, Any]:
        """转换为Reddit平台格式"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "description": self.bio,
            "persona": self.persona,
            "user_char": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
        }
        
        # 添加额外人设信息（如果有）
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_twitter_format(self) -> Dict[str, Any]:
        """转换为Twitter平台格式"""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,  # OASIS 库要求字段名为 username（无下划线）
            "name": self.name,
            "bio": self.bio,
            "description": self.bio,  # zep_tools.py expects 'description'
            "persona": self.persona,
            "user_char": self.persona,  # OASIS library expects 'user_char'
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
        }
        
        # 添加额外人设信息
        if self.age:
            profile["age"] = self.age
        if self.gender:
            profile["gender"] = self.gender
        if self.mbti:
            profile["mbti"] = self.mbti
        if self.country:
            profile["country"] = self.country
        if self.profession:
            profile["profession"] = self.profession
        if self.interested_topics:
            profile["interested_topics"] = self.interested_topics
        
        return profile
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为完整字典格式"""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "age": self.age,
            "gender": self.gender,
            "mbti": self.mbti,
            "country": self.country,
            "profession": self.profession,
            "interested_topics": self.interested_topics,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "created_at": self.created_at,
        }


class OasisProfileGenerator:
    """
    OASIS Profile生成器
    
    将Zep图谱中的实体转换为OASIS模拟所需的Agent Profile
    
    优化特性：
    1. 调用Zep图谱检索功能获取更丰富的上下文
    2. 生成非常详细的人设（包括基本信息、职业经历、性格特征、社交媒体行为等）
    3. 区分个人实体和抽象群体实体
    """
    
    # MBTI类型列表
    MBTI_TYPES = [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP"
    ]
    
    # 常见国家列表
    COUNTRIES = [
        "China", "US", "UK", "Japan", "Germany", "France", 
        "Canada", "Australia", "Brazil", "India", "South Korea"
    ]
    
    # 个人类型实体（需要生成具体人设）
    INDIVIDUAL_ENTITY_TYPES = [
        "student", "alumni", "professor", "person", "publicfigure", 
        "expert", "faculty", "official", "journalist", "activist"
    ]
    
    # 群体/机构类型实体（需要生成群体代表人设）
    GROUP_ENTITY_TYPES = [
        "university", "governmentagency", "organization", "ngo", 
        "mediaoutlet", "company", "institution", "group", "community"
    ]
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        zep_api_key: Optional[str] = None,
        graph_id: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model_name = model_name or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Zep客户端用于检索丰富上下文
        self.zep_api_key = zep_api_key or Config.ZEP_API_KEY
        self.zep_client = None
        self.graph_id = graph_id
        
        if self.zep_api_key:
            try:
                self.zep_client = Zep(api_key=self.zep_api_key)
            except Exception as e:
                logger.warning(f"Zep客户端初始化失败: {e}")

    def generate_default_profiles(
        self,
        count: int = 3,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        当图谱为空时，生成默认的Agent人设
        """
        logger.info(f"生成 {count} 个默认人设...")
        profiles = []
        
        default_names = [
            ("Analyste_Expert", "Expert Analyst with 15 years of experience in market microstructure and ICT concepts."),
            ("Trader_Retail", "Aggressive retail trader focusing on ORB breakouts and liquidity sweeps."),
            ("Observateur_IA", "AI-driven market observer analyzing sentiment and high-impact macro events."),
            ("Scalper_Pro", "Professional scalper looking for fvg gaps and order block reversals."),
            ("Macro_Watcher", "Macro-economist focusing on CPI, FOMC and high-impact news delivery.")
        ]
        
        for i in range(min(count, len(default_names))):
            name, bio = default_names[i]
            user_name = self._generate_username(name)
            
            profile = OasisAgentProfile(
                user_id=1000 + i,
                user_name=user_name,
                name=name,
                bio=bio,
                persona=f"{name} is a virtual agent created to analyze the provided data context. {bio}",
                karma=random.randint(1000, 5000),
                friend_count=random.randint(100, 300),
                follower_count=random.randint(200, 1000),
                statuses_count=random.randint(500, 2000),
                age=random.randint(25, 55),
                gender=random.choice(["male", "female"]),
                mbti=random.choice(self.MBTI_TYPES),
                country="France",
                profession=name.split('_')[0],
                interested_topics=["Trading", "Markets", "Economics"]
            )
            profiles.append(profile)
            
        return profiles

    def generate_profiles_from_entities(
        self,
        entities: List[EntityNode],
        use_llm: bool = True,
        progress_callback: Optional[callable] = None,
        graph_id: Optional[str] = None,
        parallel_count: int = 3,
        realtime_output_path: Optional[str] = None,
        output_platform: str = "reddit"
    ) -> List[OasisAgentProfile]:
        """
        批量从实体生成Agent Profile
        
        Args:
            entities: 实体列表
            use_llm: 是否使用LLM生成详细人设
            progress_callback: 进度回调 (current, total, message)
            graph_id: Zep图谱ID（用于检索）
            parallel_count: 并行处理数量
            realtime_output_path: 实时保存路径
            output_platform: 输出平台类型
            
        Returns:
            List[OasisAgentProfile]
        """
        # 设置graph_id以启用Zep检索功能
        if graph_id:
            self.graph_id = graph_id
            
        profiles = []
        total = len(entities)
        
        if total == 0:
            logger.info("图谱中无实体，生成默认推荐人设...")
            return self.generate_default_profiles(count=5, output_platform=output_platform)

        logger.info(f"开始批量生成人设: count={total}, use_llm={use_llm}, parallel={parallel_count}")

        # 准备并行处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
            # 提交生成任务
            # ID从1000开始，递增
            future_to_entity = {
                executor.submit(self.generate_profile_from_entity, entity, 1000 + i, use_llm): (i, entity)
                for i, entity in enumerate(entities)
            }
            
            for future in concurrent.futures.as_completed(future_to_entity):
                idx, entity = future_to_entity[future]
                try:
                    profile = future.result()
                    profiles.append(profile)
                    
                    # 进度更新
                    if progress_callback:
                        progress_callback(len(profiles), total, f"{entity.name}")
                    
                    # 实时保存，确保即便中断也能保留已生成的数据
                    if realtime_output_path:
                        self.save_profiles(profiles, realtime_output_path, output_platform)
                        
                except Exception as e:
                    logger.error(f"生成 {entity.name} 的人设时发生意料之外的错误: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    # 失败时降级为规则生成，确保模拟能继续
                    try:
                        fallback_profile = self.generate_profile_from_entity(entity, 1000 + idx, use_llm=False)
                        profiles.append(fallback_profile)
                    except:
                        pass
        
        # 按ID排序保持稳定性
        profiles.sort(key=lambda x: x.user_id)
        
        # 最终保存一次
        if realtime_output_path:
            self.save_profiles(profiles, realtime_output_path, output_platform)
            
        logger.info(f"批量生成完成: 成功 {len(profiles)}/{total}")
        return profiles
    
    def generate_profile_from_entity(
        self, 
        entity: EntityNode, 
        user_id: int,
        use_llm: bool = True
    ) -> OasisAgentProfile:
        """
        从Zep实体生成OASIS Agent Profile
        
        Args:
            entity: Zep实体节点
            user_id: 用户ID（用于OASIS）
            use_llm: 是否使用LLM生成详细人设
            
        Returns:
            OasisAgentProfile
        """
        entity_type = entity.get_entity_type() or "Entity"
        
        # 基础信息
        name = entity.name
        user_name = self._generate_username(name)
        
        # 构建上下文信息
        context = self._build_entity_context(entity)
        
        if use_llm:
            # 使用LLM生成详细人设
            profile_data = self._generate_profile_with_llm(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes,
                context=context
            )
        else:
            # 使用规则生成基础人设
            profile_data = self._generate_profile_rule_based(
                entity_name=name,
                entity_type=entity_type,
                entity_summary=entity.summary,
                entity_attributes=entity.attributes
            )
        
        return OasisAgentProfile(
            user_id=user_id,
            user_name=user_name,
            name=name,
            bio=profile_data.get("bio", f"{entity_type}: {name}"),
            persona=profile_data.get("persona", entity.summary or f"A {entity_type} named {name}."),
            karma=profile_data.get("karma", random.randint(500, 5000)),
            friend_count=profile_data.get("friend_count", random.randint(50, 500)),
            follower_count=profile_data.get("follower_count", random.randint(100, 1000)),
            statuses_count=profile_data.get("statuses_count", random.randint(100, 2000)),
            age=profile_data.get("age"),
            gender=profile_data.get("gender"),
            mbti=profile_data.get("mbti"),
            country=profile_data.get("country"),
            profession=profile_data.get("profession"),
            interested_topics=profile_data.get("interested_topics", []),
            source_entity_uuid=entity.uuid,
            source_entity_type=entity_type,
        )
    
    def _generate_username(self, name: str) -> str:
        """生成用户名"""
        # 移除特殊字符，转换为小写
        username = name.lower().replace(" ", "_")
        username = ''.join(c for c in username if c.isalnum() or c == '_')
        
        # 添加随机后缀避免重复
        suffix = random.randint(100, 999)
        return f"{username}_{suffix}"
    
    def _search_zep_for_entity(self, entity: EntityNode) -> Dict[str, Any]:
        """
        使用Zep图谱混合搜索功能获取实体相关的丰富信息
        
        Zep没有内置混合搜索接口，需要分别搜索edges和nodes然后合并结果。
        使用并行请求同时搜索，提高效率。
        
        Args:
            entity: 实体节点对象
            
        Returns:
            包含facts, node_summaries, context的字典
        """
        import concurrent.futures
        
        if not self.zep_client:
            return {"facts": [], "node_summaries": [], "context": ""}
        
        entity_name = entity.name
        
        results = {
            "facts": [],
            "node_summaries": [],
            "context": ""
        }
        
        # 必须有graph_id才能进行搜索
        if not self.graph_id:
            logger.debug(f"跳过Zep检索：未设置graph_id")
            return results
        
        comprehensive_query = f"关于{entity_name}的所有信息、活动、事件、关系和背景"
        
        def search_edges():
            """搜索边（事实/关系）- 带重试机制"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=30,
                        scope="edges",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep边搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep边搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        def search_nodes():
            """搜索节点（实体摘要）- 带重试机制"""
            max_retries = 3
            last_exception = None
            delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.zep_client.graph.search(
                        query=comprehensive_query,
                        graph_id=self.graph_id,
                        limit=20,
                        scope="nodes",
                        reranker="rrf"
                    )
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.debug(f"Zep节点搜索第 {attempt + 1} 次失败: {str(e)[:80]}, 重试中...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.debug(f"Zep节点搜索在 {max_retries} 次尝试后仍失败: {e}")
            return None
        
        try:
            # 并行执行edges和nodes搜索
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                edge_future = executor.submit(search_edges)
                node_future = executor.submit(search_nodes)
                
                # 获取结果
                edge_result = edge_future.result(timeout=30)
                node_result = node_future.result(timeout=30)
            
            # 处理边搜索结果
            all_facts = set()
            if edge_result and hasattr(edge_result, 'edges') and edge_result.edges:
                for edge in edge_result.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        all_facts.add(edge.fact)
            results["facts"] = list(all_facts)
            
            # 处理节点搜索结果
            all_summaries = set()
            if node_result and hasattr(node_result, 'nodes') and node_result.nodes:
                for node in node_result.nodes:
                    if hasattr(node, 'summary') and node.summary:
                        all_summaries.add(node.summary)
                    if hasattr(node, 'name') and node.name and node.name != entity_name:
                        all_summaries.add(f"相关实体: {node.name}")
            results["node_summaries"] = list(all_summaries)
            
            # 构建综合上下文
            context_parts = []
            if results["facts"]:
                context_parts.append("事实信息:\n" + "\n".join(f"- {f}" for f in results["facts"][:20]))
            if results["node_summaries"]:
                context_parts.append("相关实体:\n" + "\n".join(f"- {s}" for s in results["node_summaries"][:10]))
            results["context"] = "\n\n".join(context_parts)
            
            logger.info(f"Zep混合检索完成: {entity_name}, 获取 {len(results['facts'])} 条事实, {len(results['node_summaries'])} 个相关节点")
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Zep检索超时 ({entity_name})")
        except Exception as e:
            logger.warning(f"Zep检索失败 ({entity_name}): {e}")
        
        return results
    
    def _build_entity_context(self, entity: EntityNode) -> str:
        """
        构建实体的完整上下文信息
        
        包括：
        1. 实体本身的边信息（事实）
        2. 关联节点的详细信息
        3. Zep混合检索到的丰富信息
        """
        context_parts = []
        
        # 1. 添加实体属性信息
        if entity.attributes:
            attrs = []
            for key, value in entity.attributes.items():
                if value and str(value).strip():
                    attrs.append(f"- {key}: {value}")
            if attrs:
                context_parts.append("### 实体属性\n" + "\n".join(attrs))
        
        # 2. 添加相关边信息（事实/关系）
        existing_facts = set()
        if entity.related_edges:
            relationships = []
            for edge in entity.related_edges:  # 不限制数量
                fact = edge.get("fact", "")
                edge_name = edge.get("edge_name", "")
                direction = edge.get("direction", "")
                
                if fact:
                    relationships.append(f"- {fact}")
                    existing_facts.add(fact)
                elif edge_name:
                    if direction == "outgoing":
                        relationships.append(f"- {entity.name} --[{edge_name}]--> (相关实体)")
                    else:
                        relationships.append(f"- (相关实体) --[{edge_name}]--> {entity.name}")
            
            if relationships:
                context_parts.append("### 相关事实和关系\n" + "\n".join(relationships))
        
        # 3. 添加关联节点的详细信息
        if entity.related_nodes:
            related_info = []
            for node in entity.related_nodes:  # 不限制数量
                node_name = node.get("name", "")
                node_labels = node.get("labels", [])
                node_summary = node.get("summary", "")
                
                # 过滤掉默认标签
                custom_labels = [l for l in node_labels if l not in ["Entity", "Node"]]
                label_str = f" ({', '.join(custom_labels)})" if custom_labels else ""
                
                if node_summary:
                    related_info.append(f"- **{node_name}**{label_str}: {node_summary}")
                else:
                    related_info.append(f"- **{node_name}**{label_str}")
            
            if related_info:
                context_parts.append("### 关联实体信息\n" + "\n".join(related_info))
        
        # 4. 使用Zep混合检索获取更丰富的信息
        zep_results = self._search_zep_for_entity(entity)
        
        if zep_results.get("facts"):
            # 去重：排除已存在的事实
            new_facts = [f for f in zep_results["facts"] if f not in existing_facts]
            if new_facts:
                context_parts.append("### Zep检索到的事实信息\n" + "\n".join(f"- {f}" for f in new_facts[:15]))
        
        if zep_results.get("node_summaries"):
            context_parts.append("### Zep检索到的相关节点\n" + "\n".join(f"- {s}" for s in zep_results["node_summaries"][:10]))
        
        return "\n\n".join(context_parts)
    
    def _is_individual_entity(self, entity_type: str) -> bool:
        """判断是否是个人类型实体"""
        return entity_type.lower() in self.INDIVIDUAL_ENTITY_TYPES
    
    def _is_group_entity(self, entity_type: str) -> bool:
        """判断是否是群体/机构类型实体"""
        return entity_type.lower() in self.GROUP_ENTITY_TYPES
    
    def _generate_profile_with_llm(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> Dict[str, Any]:
        """
        使用LLM生成非常详细的人设
        
        根据实体类型区分：
        - 个人实体：生成具体的人物设定
        - 群体/机构实体：生成代表性账号设定
        """
        
        is_individual = self._is_individual_entity(entity_type)
        
        if is_individual:
            prompt = self._build_individual_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        else:
            prompt = self._build_group_persona_prompt(
                entity_name, entity_type, entity_summary, entity_attributes, context
            )
        # 尝试多次生成，直到成功或达到最大重试次数
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(is_individual)},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7 - (attempt * 0.1)  # 每次重试降低温度
                    # 不设置max_tokens，让LLM自由发挥
                )
                
                content = response.choices[0].message.content
                
                # 检查是否被截断（finish_reason不是'stop'）
                finish_reason = response.choices[0].finish_reason
                if finish_reason == 'length':
                    logger.warning(f"LLM输出被截断 (attempt {attempt+1}), 尝试修复...")
                    content = self._fix_truncated_json(content)
                
                # 尝试解析JSON
                try:
                    result = json.loads(content)
                    
                    # 验证必需字段
                    if "bio" not in result or not result["bio"]:
                        result["bio"] = entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}"
                    if "persona" not in result or not result["persona"]:
                        result["persona"] = entity_summary or f"{entity_name}是一个{entity_type}。"
                    
                    return result
                    
                except json.JSONDecodeError as je:
                    logger.warning(f"JSON解析失败 (attempt {attempt+1}): {str(je)[:80]}")
                    
                    # 尝试修复JSON
                    result = self._try_fix_json(content, entity_name, entity_type, entity_summary)
                    if result.get("_fixed"):
                        del result["_fixed"]
                        return result
                    
                    last_error = je
                    
            except Exception as e:
                logger.warning(f"LLM调用失败 (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(1 * (attempt + 1))  # 指数退避
        
        logger.warning(f"LLM生成人设失败（{max_attempts}次尝试）: {last_error}, 使用规则生成")
        return self._generate_profile_rule_based(
            entity_name, entity_type, entity_summary, entity_attributes
        )
    
    def _fix_truncated_json(self, content: str) -> str:
        """修复被截断的JSON（输出被max_tokens限制截断）"""
        import re
        
        # 如果JSON被截断，尝试闭合它
        content = content.strip()
        
        # 计算未闭合的括号
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # 检查是否有未闭合的字符串
        # 简单检查：如果最后一个引号后没有逗号或闭合括号，可能是字符串被截断
        if content and content[-1] not in '",}]':
            # 尝试闭合字符串
            content += '"'
        
        # 闭合括号
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_json(self, content: str, entity_name: str, entity_type: str, entity_summary: str = "") -> Dict[str, Any]:
        """尝试修复损坏的JSON"""
        import re
        
        # 1. 首先尝试修复被截断的情况
        content = self._fix_truncated_json(content)
        
        # 2. 尝试提取JSON部分
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # 3. 处理字符串中的换行符问题
            # 找到所有字符串值并替换其中的换行符
            def fix_string_newlines(match):
                s = match.group(0)
                # 替换字符串内的实际换行符为空格
                s = s.replace('\n', ' ').replace('\r', ' ')
                # 替换多余空格
                s = re.sub(r'\s+', ' ', s)
                return s
            
            # 匹配JSON字符串值
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string_newlines, json_str)
            
            # 4. 尝试解析
            try:
                result = json.loads(json_str)
                result["_fixed"] = True
                return result
            except json.JSONDecodeError as e:
                # 5. 如果还是失败，尝试更激进的修复
                try:
                    # 移除所有控制字符
                    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                    # 替换所有连续空白
                    json_str = re.sub(r'\s+', ' ', json_str)
                    result = json.loads(json_str)
                    result["_fixed"] = True
                    return result
                except:
                    pass
        
        # 6. 尝试从内容中提取部分信息
        bio_match = re.search(r'"bio"\s*:\s*"([^"]*)"', content)
        persona_match = re.search(r'"persona"\s*:\s*"([^"]*)', content)  # 可能被截断
        
        bio = bio_match.group(1) if bio_match else (entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}")
        persona = persona_match.group(1) if persona_match else (entity_summary or f"{entity_name}是一个{entity_type}。")
        
        # 如果提取到了有意义的内容，标记为已修复
        if bio_match or persona_match:
            logger.info(f"从损坏的JSON中提取了部分信息")
            return {
                "bio": bio,
                "persona": persona,
                "_fixed": True
            }
        
        # 7. 完全失败，返回基础结构
        logger.warning(f"JSON修复失败，返回基础结构")
        return {
            "bio": entity_summary[:200] if entity_summary else f"{entity_type}: {entity_name}",
            "persona": entity_summary or f"{entity_name}是一个{entity_type}。"
        }
    
    def _get_system_prompt(self, is_individual: bool) -> str:
        """获取系统提示词"""
        base_prompt = "你是社交媒体用户画像生成专家。生成详细、真实的人设用于舆论模拟,最大程度还原已有现实情况。必须返回有效的JSON格式，所有字符串值不能包含未转义的换行符。使用中文。"
        return base_prompt
    
    def _build_individual_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """构建个人实体的详细人设提示词"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""为实体生成详细的社交媒体用户人设,最大程度还原已有现实情况。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 社交媒体简介，200字
2. persona: 详细人设描述（2000字的纯文本），需包含:
   - 基本信息（年龄、职业、教育背景、所在地）
   - 人物背景（重要经历、与事件的关联、社会关系）
   - 性格特征（MBTI类型、核心性格、情绪表达方式）
   - 社交媒体行为（发帖频率、内容偏好、互动风格、语言特点）
   - 立场观点（对话题的态度、可能被激怒/感动的内容）
   - 独特特征（口头禅、特殊经历、个人爱好）
   - 个人记忆（人设的重要部分，要介绍这个个体与事件的关联，以及这个个体在事件中的已有动作与反应）
3. age: 年龄数字（必须是整数）
4. gender: 性别，必须是英文: "male" 或 "female"
5. mbti: MBTI类型（如INTJ、ENFP等）
6. country: 国家（使用中文，如"中国"）
7. profession: 职业
8. interested_topics: 感兴趣话题数组

重要:
- 所有字段值必须是字符串 or 数字，不要使用换行符
- persona 必须是一段连贯的文字描述
- 使用中文（除了gender字段必须用英文male/female）
- 内容要与实体信息保持一致
- age必须是有效的整数，gender必须是"male"或"female"
"""

    def _build_group_persona_prompt(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any],
        context: str
    ) -> str:
        """构建群体/机构实体的详细人设提示词"""
        
        attrs_str = json.dumps(entity_attributes, ensure_ascii=False) if entity_attributes else "无"
        context_str = context[:3000] if context else "无额外上下文"
        
        return f"""为机构/群体实体生成详细的社交媒体账号设定,最大程度还原已有现实情况。

实体名称: {entity_name}
实体类型: {entity_type}
实体摘要: {entity_summary}
实体属性: {attrs_str}

上下文信息:
{context_str}

请生成JSON，包含以下字段:

1. bio: 官方账号简介，200字，专业得体
2. persona: 详细账号设定描述（2000字的纯文本），需包含:
   - 机构基本信息（正式名称、机构性质、成立背景、主要职能）
   - 账号定位（账号类型、目标受众、核心功能）
   - 发言风格（语言特点、常用表达、禁忌话题）
   - 发布内容特点（内容类型、发布频率、活跃时间段）
   - 立场态度（对核心话题的官方立场、面对争议的处理方式）
   - 特殊说明（代表的群体画像、运营习惯）
   - 机构记忆（机构人设的重要部分，要介绍这个机构与事件的关联，以及这个机构在事件中的已有动作与反应）
3. age: 固定填30（机构账号的虚拟年龄）
4. gender: 固定填"other"（机构账号使用other表示非个人）
5. mbti: MBTI类型，用于描述账号风格，如ISTJ代表严谨保守
6. country: 国家（使用中文，如"中国"）
7. profession: 机构职能描述
8. interested_topics: 关注领域数组

重要:
- 所有字段值必须是字符串 or 数字，不允许null值
- persona必须是一段连贯的文字描述，不要使用换行符
- 使用中文（除了gender字段必须用英文"other"）
- age必须是整数30，gender必须是字符串"other"
- 机构账号发言要符合其身份定位"""
    
    def _generate_profile_rule_based(
        self,
        entity_name: str,
        entity_type: str,
        entity_summary: str,
        entity_attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用规则生成基础人设"""
        
        # 根据实体类型生成不同的人设
        entity_type_lower = entity_type.lower()
        
        if entity_type_lower in ["student", "alumni"]:
            return {
                "bio": f"{entity_type} with interests in academics and social issues.",
                "persona": f"{entity_name} is a {entity_type.lower()} who is actively engaged in academic and social discussions. They enjoy sharing perspectives and connecting with peers.",
                "age": random.randint(18, 30),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": "Student",
                "interested_topics": ["Education", "Social Issues", "Technology"],
            }
        
        elif entity_type_lower in ["publicfigure", "expert", "faculty"]:
            return {
                "bio": f"Expert and thought leader in their field.",
                "persona": f"{entity_name} is a recognized {entity_type.lower()} who shares insights and opinions on important matters. They are known for their expertise and influence in public discourse.",
                "age": random.randint(35, 65),
                "gender": random.choice(["male", "female"]),
                "mbti": random.choice(self.MBTI_TYPES),
                "country": random.choice(self.COUNTRIES),
                "profession": entity_type,
                "interested_topics": ["News", "Policy", "Science"],
            }
        
        return {
            "bio": f"{entity_type}: {entity_name}",
            "persona": f"{entity_name} is a {entity_type} represented in the analysis. They have various attributes and relationships that contribute to the overall context.",
            "age": random.randint(20, 60),
            "gender": random.choice(["male", "female", "other"]),
            "mbti": random.choice(self.MBTI_TYPES),
            "country": random.choice(self.COUNTRIES),
            "profession": entity_type,
            "interested_topics": ["General"],
        }

    def save_profiles(
        self,
        profiles: List[OasisAgentProfile],
        file_path: str,
        platform: str = "reddit"
    ):
        """
        保存生成的Profile到文件
        
        Args:
            profiles: Profile列表
            file_path: 保存路径
            platform: 平台类型 (reddit/twitter)
        """
        if not profiles:
            logger.warning("没有Profile可保存")
            return

        try:
            # 确保目录存在
            import os
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            if platform == "reddit":
                # Reddit 使用 JSON 格式 (包含完整的 profile 对象)
                data = [p.to_reddit_format() for p in profiles]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存 {len(profiles)} 个 Reddit Profile 到 {file_path}")
                
            elif platform == "twitter":
                # Twitter 必须使用 CSV 格式，这是 OASIS 原生运行脚本的要求
                fieldnames = [
                    "user_id", "username", "name", "bio", "description", 
                    "persona", "user_char",
                    "friend_count", "follower_count", "statuses_count", "created_at",
                    "age", "gender", "mbti", "country", "profession", "interested_topics"
                ]
                
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for p in profiles:
                        data = p.to_twitter_format()
                        # interested_topics 在 CSV 中需要转换为字符串
                        if isinstance(data.get("interested_topics"), list):
                            data["interested_topics"] = ",".join(data["interested_topics"])
                        writer.writerow(data)
                
                logger.info(f"已保存 {len(profiles)} 个 Twitter Profile 到 {file_path}")
                
            else:
                # 默认 JSON 导出（完整格式）
                data = [p.to_dict() for p in profiles]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"已保存 {len(profiles)} 个 Profile 到 {file_path}")
                
        except Exception as e:
            logger.error(f"保存Profile失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
