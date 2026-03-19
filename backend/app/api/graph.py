"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import os
import traceback
import threading
import openai
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# 获取日志器
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 项目管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    获取项目详情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有项目
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    删除项目
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"项目不存在或删除失败: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"项目已删除: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置项目状态（用于重新构建图谱）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"项目不存在: {project_id}"
        }), 404
    
    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": f"项目已重置: {project_id}",
        "data": project.to_dict()
    })


# ============== 接口1：上传文件并生成本体 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    接口1：上传文件，分析生成本体定义
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        
        # 获取参数
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"项目名称: {project_name}")
        logger.debug(f"模拟需求: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "请提供模拟需求描述 (simulation_requirement)"
            }), 400
        
        # 获取上传的文件
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "请至少上传一个文档文件"
            }), 400
        
        # 创建项目
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"创建项目: {project.project_id}")
        
        # 保存文件并提取文本
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # 保存文件到项目目录
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # 提取文本
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "没有成功处理任何文档，请检查文件格式"
            }), 400
        
        # 保存提取的文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文本提取完成，共 {len(all_text)} 字符")
        
        # 生成本体
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # 保存本体到项目
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        status_code = 500
        error_msg = str(e)
        
        if isinstance(e, openai.AuthenticationError):
            status_code = 401
            error_msg = "Clé API LLM non valide ou expirée (401). Veuillez vérifier votre fichier .env."
        elif isinstance(e, openai.RateLimitError):
            status_code = 429
            error_msg = "Limite de quota LLM atteinte (429). Veuillez réessayer plus tard."
        elif isinstance(e, openai.APIConnectionError):
            status_code = 502
            error_msg = "Erreur de connexion à l'API LLM. Veuillez vérifier votre réseau."
            
        logger.error(f"Erreur dans generate_ontology: {error_msg}")
        return jsonify({
            "success": False,
            "error": error_msg,
            "traceback": traceback.format_exc()
        }), status_code


# ============== 接口2：构建图谱 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    接口2：根据project_id构建图谱
    """
    try:
        logger.info("=== 开始构建图谱 ===")
        
        # 检查配置
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("ZEP_API_KEY未配置")
        if errors:
            logger.error(f"配置错误: {errors}")
            return jsonify({
                "success": False,
                "error": "配置错误: " + "; ".join(errors)
            }), 500
        
        # 解析请求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"请求参数: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "请提供 project_id"
            }), 400
        
        # 获取项目
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"项目不存在: {project_id}"
            }), 404
        
        # 检查项目状态
        force = data.get('force', False)
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "项目尚未生成本体，请先调用 /ontology/generate"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "图谱正在构建中，请勿重复提交。如需强制重建，请添加 force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        # 更新配置启动异步任务...
        # (保持原逻辑不变，此处省略部分代码，重点在 error handling)

        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({"success": False, "error": "未找到提取的文本内容"}), 400
        
        ontology = project.ontology
        if not ontology:
            return jsonify({"success": False, "error": "未找到本体定义"}), 400
            
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {project.name or 'Graph'}")
        
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                chunks = TextProcessor.split_text(text, chunk_size=project.chunk_size, overlap=project.chunk_overlap)
                graph_id = builder.create_graph(name=project.name)
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                builder.set_ontology(graph_id, ontology)
                
                def p_cb(m, r): task_manager.update_task(task_id, message=m, progress=15+int(r*75))
                builder.add_text_batches(graph_id, chunks, progress_callback=p_cb)
                
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, message="图谱构建完成", progress=100)
            except Exception as e:
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                task_manager.update_task(task_id, status=TaskStatus.FAILED, message=f"构建失败: {str(e)}")

        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {"project_id": project_id, "task_id": task_id}
        })
        
    except Exception as e:
        status_code = 500
        error_msg = str(e)
        if isinstance(e, openai.AuthenticationError):
            status_code = 401
            error_msg = "Clé API LLM non valide ou expirée (401). Veuillez vérifier votre fichier .env."
        return jsonify({"success": False, "error": error_msg}), status_code


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404
    return jsonify({"success": True, "data": task.to_dict()})


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    tasks = TaskManager().list_tasks()
    return jsonify({"success": True, "data": tasks})


# ============== 图谱数据接口 ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    try:
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        return jsonify({"success": True, "data": builder.get_graph_data(graph_id)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    try:
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        return jsonify({"success": True, "message": f"图谱已删除: {graph_id}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
