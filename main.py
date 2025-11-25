from fastapi import FastAPI, Request, HTTPException, Form, Depends
from starlette.responses import RedirectResponse
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from nicegui import app, ui
from sqlalchemy.orm import Session
import models
from database import SessionLocal, engine
import secrets
import logging
import asyncio
import traceback
from typing import Annotated, List, Union, Optional
from base import Base  # 从基础模块导入
from models import User, UserSession, Role  # 导入用户、用户会话和角色模型
from sqlalchemy.orm import joinedload
from contextlib import asynccontextmanager
from pydantic import BaseModel, ValidationError

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 定义 lifespan 事件处理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行的代码
    global db_session
    db_session = SessionLocal()
    logging.info("应用启动")
    
    # 初始化用户（如果不存在）
    try:
        init_users(db_session)
        logging.info("用户初始化完成")
    except Exception as e:
        logging.error(f"用户初始化失败: {str(e)}")
    
    yield  # 应用运行期间
    
    # 关闭时执行的代码
    db_session.close()
    logging.info("应用关闭")

# 创建 FastAPI 应用实例，使用 lifespan 替代 on_event
app = FastAPI(title="NiceGUI + PostgreSQL 管理系统", lifespan=lifespan)

# 添加 CORS 中间件（如果需要跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 密码流
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="api/login",
    scopes={
        "questions:read": "查看问题",
        "questions:write": "创建或修改问题",
        "questions:delete": "删除问题",
        "process:config": "配置流程"
    }
)

# 定义用户模型，包含权限范围
class TokenData(BaseModel):
    username: str | None = None
    scopes: List[str] = []

# 认证相关函数
def get_current_user(request: Request):
    """验证用户是否已登录"""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 从数据库获取会话信息
    db = SessionLocal()
    try:
        session = db.query(UserSession).filter(UserSession.session_token == token).first()
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 将数据库会话对象转换为字典
        user_session = {
            "username": session.username,
            "role": session.role,
            "scopes": session.scopes.split(",") if session.scopes else []
        }
        return user_session
    finally:
        db.close()

async def get_current_active_user(
    security_scopes: SecurityScopes, 
    request: Request
):
    """验证用户是否有足够的权限执行操作"""
    user_session = get_current_user(request)
    
    if not security_scopes.scopes:
        return user_session
    
    # 检查用户是否有足够的权限
    user_scopes = user_session.get("scopes", [])
    for scope in security_scopes.scopes:
        if scope not in user_scopes:
            raise HTTPException(
                status_code=403,
                detail="权限不足",
                headers={"WWW-Authenticate": f"Bearer scope={security_scopes.scope_str}"},
            )
    return user_session

# 问题管理 API 端点
@app.get("/api/questions")
async def get_questions(current_user: dict = Depends(get_current_active_user)):
    """获取所有问题"""
    # 检查权限
    if "questions:read" not in current_user.get("scopes", []):
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        db = SessionLocal()
        questions = db.query(models.Questions).all()
        
        # 转换为字典格式
        result = []
        for question in questions:
            choices = []
            for choice in question.choices:
                choices.append({
                    "id": choice.id,
                    "choice_text": choice.choice_text,
                    "is_correct": choice.is_correct
                })
            
            result.append({
                "id": question.id,
                "question_text": question.question_text,
                "choices": choices
            })
        
        db.close()
        return result
    except Exception as e:
        logging.error(f"获取问题列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取问题列表失败")

@app.post("/api/questions")
async def create_question(question_data: dict, current_user: dict = Depends(get_current_active_user)):
    """创建新问题"""
    # 检查权限
    if "questions:write" not in current_user.get("scopes", []):
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        db = SessionLocal()
        
        # 创建问题
        question = models.Questions(
            question_text=question_data["question_text"]
        )
        db.add(question)
        db.flush()  # 获取问题ID但不提交事务
        
        # 创建选项
        for choice_data in question_data["choices"]:
            choice = models.Choices(
                choice_text=choice_data["choice_text"],
                is_correct=choice_data["is_correct"],
                question_id=question.id
            )
            db.add(choice)
        
        db.commit()
        db.refresh(question)
        db.close()
        
        return {"message": "问题创建成功", "question_id": question.id}
    except Exception as e:
        db.rollback()
        db.close()
        logging.error(f"创建问题失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建问题失败")

@app.delete("/api/questions/{question_id}")
async def delete_question(question_id: int, current_user: dict = Depends(get_current_active_user)):
    """删除问题"""
    # 检查权限
    if "questions:delete" not in current_user.get("scopes", []):
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        db = SessionLocal()
        question = db.query(models.Questions).filter(models.Questions.id == question_id).first()
        
        if not question:
            db.close()
            raise HTTPException(status_code=404, detail="问题未找到")
        
        # 删除关联的选项
        db.query(models.Choices).filter(models.Choices.question_id == question_id).delete()
        
        # 删除问题
        db.delete(question)
        db.commit()
        db.close()
        
        return {"message": "问题删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        db.close()
        logging.error(f"删除问题失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除问题失败")

# 添加根路径重定向到登录页面
@app.get("/")
def redirect_to_gui():
    return RedirectResponse(url="/gui/login")

# 主页路由（自动挂载在/gui/路径下）
@ui.page("/")
def main_page(request: Request):
    # 完全移除认证检查和重定向
    # 简单显示主页内容，让登录页面单独处理认证
    ui.add_head_html("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    ui.query(".nicegui-content").classes("p-6")
    
    # 简单检查用户状态 - 从数据库获取会话信息
    token = request.cookies.get("session_token")
    user = None  # 初始化user变量
    if token:
        # 从数据库获取会话信息
        db = SessionLocal()
        try:
            session = db.query(UserSession).filter(UserSession.session_token == token).first()
            if session:
                # 将数据库会话对象转换为字典
                user = {
                    "username": session.username,
                    "role": session.role,
                    "scopes": session.scopes.split(",") if session.scopes else []
                }
        finally:
            db.close()
    
    # 顶部导航栏
    with ui.header(elevated=True).classes("items-center justify-between"):
        ui.label("📝 数据库管理系统").classes("text-xl font-bold")
        with ui.row().classes("gap-2"):
            if user:
                ui.label(f"👤 {user['username']} (角色: {user.get('role', '未知')})")
                # 定义退出登录函数
                def logout():
                    # 从数据库中删除会话信息
                    token = request.cookies.get("session_token")  # 重新获取token
                    if token:
                        db = SessionLocal()
                        try:
                            session = db.query(UserSession).filter(UserSession.session_token == token).first()
                            if session:
                                db.delete(session)
                                db.commit()
                        finally:
                            db.close()
                    
                    # 清除cookie并重定向到登录页面
                    js_code = """
                    document.cookie = "session_token=; path=/gui; expires=Thu, 01 Jan 1970 00:00:00 GMT";
                    window.location.href = "/gui/login";
                    """
                    ui.run_javascript(js_code)
                ui.button("🚪 退出登录", on_click=logout, color="red")
            else:
                ui.label("未登录")
                ui.button("🔐 登录", on_click=lambda: ui.run_javascript('window.location.href = "/gui/login"'))

    # 已登录，显示主页内容
    if user:
        # 在早期定义对话框，确保它们在整个函数中的可访问性
        # 流程配置对话框
        global process_config_dialog
        process_config_dialog = ui.dialog()
        
        # 创建问题对话框
        global create_dialog
        create_dialog = ui.dialog()
        
        # 重置函数 - 在对话框打开时重新初始化
        def reset_process_config():
            pass  # 重置逻辑已在add_process_step中实现
        
        with process_config_dialog, ui.card().classes("p-6 w-full max-w-4xl"):
            ui.label("⚙️ 流程配置").classes("text-xl font-bold mb-4")
            
            # 添加滚动区域容器
            with ui.scroll_area().classes("h-96 w-full"):
                # 初始化工步容器
                process_steps_container = ui.column().classes("w-full mb-4 border border-gray-200 rounded-lg overflow-hidden")
                process_steps = []
                
                # 工步类型选项
                step_types = ["CC-CV", "CC", "DC", "Rest", "END"]
                
                def add_process_step(step_data=None):
                    # 工步序号
                    step_index = len(process_steps) + 1
                    
                    with process_steps_container:
                        with ui.row().classes("w-full items-center p-2 hover:bg-gray-50 transition-colors border-t border-gray-200") as step_row:
                            # 序号显示
                            ui.label(str(step_index)).classes("w-12 text-center text-gray-600")
                            
                            # 工步类型选择
                            if step_data and hasattr(step_data, 'step_type'):
                                step_type = ui.select(step_types, value=step_data.step_type).classes("w-24 ml-2")
                            else:
                                step_type = ui.select(step_types, value="CC-CV").classes("w-24 ml-2")
                            
                            # 电流输入
                            current_value = step_data.current if step_data and hasattr(step_data, 'current') and step_data.current else "2.000"
                            current_input = ui.input(value=str(current_value)).classes("w-28 ml-2")
                            
                            # 截止电压输入
                            voltage_value = step_data.voltage if step_data and hasattr(step_data, 'voltage') and step_data.voltage else "3.650"
                            voltage_input = ui.input(value=str(voltage_value)).classes("w-32 ml-2")
                            
                            # 截止电流输入
                            end_current_value = step_data.end_current if step_data and hasattr(step_data, 'end_current') and step_data.end_current else "0.005"
                            end_current_input = ui.input(value=str(end_current_value)).classes("w-32 ml-2")
                            
                            # 时间输入
                            time_value = step_data.step_time if step_data and hasattr(step_data, 'step_time') and step_data.step_time else "00:00:00"
                            time_input = ui.input(value=time_value).classes("w-28 ml-2")
                            
                            # 容量复选框
                            capacity_value = step_data.capacity_check if step_data and hasattr(step_data, 'capacity_check') else False
                            capacity_check = ui.checkbox(value=capacity_value).classes("ml-2 w-12")
                            
                            # 温度补偿复选框
                            temp_comp_value = step_data.temp_compensation if step_data and hasattr(step_data, 'temp_compensation') else False
                            temp_comp_check = ui.checkbox(value=temp_comp_value).classes("ml-2 w-16")
                            
                            # 删除按钮
                            def remove_step():
                                # 从容器中移除行
                                process_steps_container.remove(step_data_dict['row'])
                                # 从数组中移除
                                process_steps.remove(step_data_dict)
                                # 重新编号
                                for i, step in enumerate(process_steps):
                                    step['row'].clear()
                                    with step['row']:
                                        ui.label(str(i+1)).classes("w-12 text-center text-gray-600")
                                        ui.select(step_types, value=step['type'].value).classes("w-24 ml-2")
                                        ui.input(value=step['current'].value).classes("w-28 ml-2")
                                        ui.input(value=step['voltage'].value).classes("w-32 ml-2")
                                        ui.input(value=step['end_current'].value).classes("w-32 ml-2")
                                        ui.input(value=step['time'].value).classes("w-28 ml-2")
                                        ui.checkbox(value=step['capacity'].value).classes("ml-2 w-12")
                                        ui.checkbox(value=step['temp_comp'].value).classes("ml-2 w-16")
                                        ui.button("🗑️", on_click=remove_step).classes("ml-2 text-red-500 hover:text-red-700")
                            
                            # 删除按钮
                            ui.button("🗑️", on_click=remove_step).classes("ml-2 text-red-500 hover:text-red-700")
                            
                            # 保存步骤数据
                            step_data_dict = {
                                'row': step_row,
                                'index': step_index,
                                'type': step_type,
                                'current': current_input,
                                'voltage': voltage_input,
                                'end_current': end_current_input,
                                'time': time_input,
                                'capacity': capacity_check,
                                'temp_comp': temp_comp_check
                            }
                            process_steps.append(step_data_dict)
                
                # 初始化表头
                with process_steps_container:
                    with ui.row().classes("w-full bg-gray-100 p-2 font-medium"):
                        ui.label("工步").classes("w-12 text-center")
                        ui.label("类型").classes("w-24")
                        ui.label("电流/A").classes("w-28")
                        ui.label("截止电压/V").classes("w-32")
                        ui.label("截止电流/A").classes("w-32")
                        ui.label("HH:MM:SS").classes("w-28")
                        ui.label("容量").classes("w-12")
                        ui.label("温度补偿").classes("w-16")
                        ui.label("操作").classes("w-12")
                
                # 添加加载配置的函数
                def load_saved_config():
                    # 清空现有步骤
                    process_steps.clear()
                    process_steps_container.clear()
                    
                    # 重新添加表头
                    with process_steps_container:
                        with ui.row().classes("w-full bg-gray-100 p-2 font-medium"):
                            ui.label("工步").classes("w-12 text-center")
                            ui.label("类型").classes("w-24")
                            ui.label("电流/A").classes("w-28")
                            ui.label("截止电压/V").classes("w-32")
                            ui.label("截止电流/A").classes("w-32")
                            ui.label("HH:MM:SS").classes("w-28")
                            ui.label("容量").classes("w-12")
                            ui.label("温度补偿").classes("w-16")
                            ui.label("操作").classes("w-12")
                    
                    # 从数据库加载配置
                    saved_steps = asyncio.run(load_process_config())
                    if saved_steps:
                        for step in saved_steps:
                            add_process_step(step)
                    else:
                        # 默认添加一个工步
                        add_process_step()
                
                # 监听对话框打开事件
                process_config_dialog.on('show', load_saved_config)
                
                # 添加默认工步的函数
                def add_default_step():
                    add_process_step()
                
                # 监听对话框打开事件
                process_config_dialog.on('show', load_saved_config)
                
                # 初始化时添加一个默认工步
                add_default_step()
            
            with ui.row().classes("w-full justify-between items-center mb-4"):
                ui.button("➕ 添加工步", on_click=add_process_step)
            
            # 添加保存流程配置函数
            def save_process_config():
                """保存流程配置到数据库"""
                try:
                    # 收集所有工步数据
                    process_data = []
                    for step in process_steps:
                        step_data = {
                            'index': step['index'],
                            'type': step['type'].value,
                            'current': step['current'].value,
                            'voltage': step['voltage'].value,
                            'end_current': step['end_current'].value,
                            'time': step['time'].value,
                            'capacity': step['capacity'].value,
                            'temp_comp': step['temp_comp'].value
                        }
                        process_data.append(step_data)
                    
                    # 保存到数据库
                    db = SessionLocal()
                    try:
                        # 清除现有的流程配置
                        db.query(models.ProcessStep).delete()
                        
                        # 添加新的流程配置
                        for step_data in process_data:
                            process_step = models.ProcessStep(
                                step_index=step_data['index'],
                                step_type=step_data['type'],
                                current=float(step_data['current']) if step_data['current'] else None,
                                voltage=float(step_data['voltage']) if step_data['voltage'] else None,
                                end_current=float(step_data['end_current']) if step_data['end_current'] else None,
                                step_time=step_data['time'],
                                capacity_check=step_data['capacity'],
                                temp_compensation=step_data['temp_comp']
                            )
                            db.add(process_step)
                        
                        db.commit()
                        ui.notify(f"成功保存 {len(process_data)} 个工步配置到数据库", type="positive")
                        process_config_dialog.close()
                        reset_process_config()  # 重置表单状态
                        
                    except Exception as e:
                        db.rollback()
                        ui.notify(f"保存配置到数据库失败: {str(e)}", type="negative")
                        logging.error(f"保存流程配置失败: {str(e)}")
                    finally:
                        db.close()
                    
                except Exception as e:
                    ui.notify(f"保存配置失败: {str(e)}", type="negative")
                    logging.error(f"保存流程配置失败: {str(e)}")
            
            # 自定义取消函数，重置状态
            def cancel_process_config():
                process_config_dialog.close()
                reset_process_config()  # 重置配置状态
            
            with ui.row().classes("justify-end gap-2 mt-4"):
                ui.button("取消", on_click=cancel_process_config)
                ui.button("保存配置", on_click=save_process_config, color="primary")
        
        with create_dialog, ui.card().classes("p-6 w-full max-w-2xl"):
            ui.label("➕ 创建新问题").classes("text-xl font-bold mb-4")
            
            # 问题内容输入
            question_input = ui.textarea("问题内容", placeholder="请输入问题内容...").classes("w-full h-32 mb-4")
            
            # 选项容器 - 表格样式
            choices_container = ui.column().classes("w-full mb-4 border border-gray-200 rounded-lg overflow-hidden")
            
            # 添加表头
            with choices_container:
                with ui.row().classes("w-full bg-gray-100 p-2 font-medium"):
                    ui.label("序号").classes("w-12 text-center")
                    ui.label("选项内容").classes("flex-1")
                    ui.label("正确答案").classes("w-20")
                    ui.label("操作").classes("w-12")
            
            choices = []
            
            def add_choice():
                # 选项序号
                choice_index = len(choices) + 1
                
                with choices_container:
                    with ui.row().classes("w-full items-center p-2 hover:bg-gray-50 transition-colors border-t border-gray-200") as choice_row:
                        # 序号显示
                        ui.label(str(choice_index)).classes("w-12 text-center text-gray-600")
                        
                        # 选项输入框
                        choice_input = ui.input(placeholder="请输入选项内容...").classes("flex-1 ml-2")
                        
                        # 正确答案复选框
                        correct_checkbox = ui.checkbox()
                        
                        # 删除按钮
                        def remove_choice():
                            # 从容器中移除行
                            choices_container.remove(choice_data['row'])
                            # 从数组中移除
                            choices.remove(choice_data)
                            # 重新编号
                            for i, choice in enumerate(choices):
                                choice['row'].clear()
                                with choice['row']:
                                    ui.label(str(i+1)).classes("w-12 text-center text-gray-600")
                                    ui.input(value=choice['input'].value, placeholder="请输入选项内容...").classes("flex-1 ml-2")
                                    ui.checkbox(value=choice['correct'].value)
                                    ui.button("🗑️", on_click=remove_choice).classes("ml-2 text-red-500 hover:text-red-700")
                        
                        # 删除按钮
                        ui.button("🗑️", on_click=remove_choice).classes("ml-2 text-red-500 hover:text-red-700")
                        
                        # 保存选项数据
                        choice_data = {
                            'row': choice_row,
                            'index': choice_index,
                            'input': choice_input,
                            'correct': correct_checkbox
                        }
                        choices.append(choice_data)
            
            # 默认添加4个选项
            for _ in range(4):
                add_choice()
            
            def save_question():
                """保存问题到数据库"""
                try:
                    # 获取问题内容
                    question_text = question_input.value.strip()
                    if not question_text:
                        ui.notify("请输入问题内容", type="negative")
                        return
                    
                    # 检查选项
                    if not choices:
                        ui.notify("请添加至少一个选项", type="negative")
                        return
                    
                    # 获取选项数据
                    choice_data = []
                    correct_count = 0
                    for choice in choices:
                        choice_text = choice['input'].value.strip()
                        is_correct = choice['correct'].value
                        
                        if not choice_text:
                            continue
                            
                        if is_correct:
                            correct_count += 1
                            
                        choice_data.append({
                            'choice_text': choice_text,
                            'is_correct': is_correct
                        })
                    
                    if not choice_data:
                        ui.notify("请添加至少一个有效选项", type="negative")
                        return
                    
                    if correct_count == 0:
                        ui.notify("请至少选择一个正确答案", type="negative")
                        return
                    
                    # 保存到数据库
                    db = SessionLocal()
                    try:
                        # 创建问题
                        question = models.Questions(question_text=question_text)
                        db.add(question)
                        db.flush()  # 获取问题ID但不提交事务
                        
                        # 创建选项
                        for choice in choice_data:
                            db_choice = models.Choices(
                                choice_text=choice['choice_text'],
                                is_correct=choice['is_correct'],
                                question_id=question.id
                            )
                            db.add(db_choice)
                        
                        db.commit()
                        ui.notify("问题创建成功", type="positive")
                        create_dialog.close()
                        
                        # 重新加载问题列表
                        asyncio.create_task(load_questions(question_list_container, user))
                    except Exception as e:
                        db.rollback()
                        ui.notify(f"保存失败: {str(e)}", type="negative")
                    finally:
                        db.close()
                except Exception as e:
                    ui.notify(f"保存过程中发生错误: {str(e)}", type="negative")
            
            with ui.row().classes("w-full justify-between items-center mt-4"):
                ui.button("➕ 添加选项", on_click=add_choice)
            
            with ui.row().classes("justify-end gap-2 mt-4"):
                ui.button("取消", on_click=create_dialog.close)
                ui.button("保存问题", on_click=save_question, color="primary")
        
        # 主页内容 - 移除顶部导航栏，让内容区域占据整个屏幕
        with ui.column().classes("w-full h-screen"):
            # 主内容区域 - 占据整个屏幕
            with ui.column().classes("flex-1 overflow-auto p-4"):
                with ui.column().classes("w-full max-w-6xl mx-auto"):
                    # 功能卡片区域
                    with ui.row().classes("w-full gap-6 mb-8"):
                        # 权限控制 - 只有具有相应权限的用户才能看到这些按钮
                        if user and "process:config" in user.get("scopes", []):
                            with ui.card().classes("flex-1 cursor-pointer hover:shadow-lg transition-shadow"):
                                with ui.card_section().classes("items-center"):
                                    ui.icon("settings").classes("text-4xl text-blue-500 mb-2")
                                    ui.label("⚙️ 流程配置").classes("text-lg font-bold")
                                    ui.label("配置和管理电池测试流程").classes("text-gray-500 text-sm")
                                ui.button("进入配置", on_click=process_config_dialog.open).classes("self-end")
                        
                        if user and "questions:write" in user.get("scopes", []):
                            with ui.card().classes("flex-1 cursor-pointer hover:shadow-lg transition-shadow"):
                                with ui.card_section().classes("items-center"):
                                    ui.icon("question_answer").classes("text-4xl text-green-500 mb-2")
                                    ui.label("➕ 创建问题").classes("text-lg font-bold")
                                    ui.label("创建新的测试问题").classes("text-gray-500 text-sm")
                                ui.button("创建问题", on_click=create_dialog.open).classes("self-end")
                    
                    # 问题列表区域
                    with ui.card().classes("w-full"):
                        with ui.card_section():
                            with ui.row().classes("w-full items-center justify-between mb-4"):
                                ui.label("📋 问题列表").classes("text-2xl font-bold")
                            
                            # 问题列表容器
                            global question_list_container
                            question_list_container = ui.column().classes("w-full")
                            print("[INFO] 问题列表容器已创建")
                    
                    # 添加底部间距
                    ui.element().classes("h-16")
                    
                    # 添加用户管理区域 - 仅管理员可见
                    if user and user.get("role") == "administrator":
                        with ui.expansion("👥 用户管理", icon="manage_accounts").classes("w-full"):
                            with ui.card().classes("w-full"):
                                # 添加创建用户按钮
                                def open_create_user_dialog():
                                    # 获取所有角色用于选择
                                    db = SessionLocal()
                                    roles = db.query(Role).all()
                                    role_options = {role.name: role.name for role in roles}
                                    db.close()
                                    
                                    with ui.dialog() as create_user_dialog, ui.card():
                                        ui.label("创建新用户").classes("text-h6")
                                        
                                        # 用户名输入
                                        username_input = ui.input(label="用户名", placeholder="输入用户名").classes("w-full")
                                        
                                        # 密码输入
                                        password_input = ui.input(label="密码", placeholder="输入密码", password=True).classes("w-full")
                                        
                                        # 角色选择
                                        role_select = ui.select(role_options, label="角色", value="user").classes("w-full")
                                        
                                        # 状态标签
                                        status_label = ui.label("").classes("w-full text-center")
                                        
                                        # 创建用户函数
                                        def create_user():
                                            username = username_input.value
                                            password = password_input.value
                                            role = role_select.value
                                            
                                            # 验证输入
                                            if not username or not password:
                                                status_label.set_text("用户名和密码不能为空")
                                                return
                                            
                                            if len(password) < 3:
                                                status_label.set_text("密码长度至少3位")
                                                return
                                            
                                            # 创建用户
                                            db = SessionLocal()
                                            try:
                                                # 检查用户名是否已存在
                                                existing_user = db.query(models.User).filter(models.User.username == username).first()
                                                if existing_user:
                                                    status_label.set_text("用户名已存在")
                                                    return
                                                
                                                # 检查角色是否存在
                                                role_exists = db.query(Role).filter(Role.name == role).first()
                                                if not role_exists:
                                                    status_label.set_text("选择的角色不存在")
                                                    return
                                                
                                                # 创建新用户
                                                new_user = models.User(username=username, role=role)
                                                new_user.set_password(password)
                                                db.add(new_user)
                                                db.commit()
                                                db.refresh(new_user)
                                                
                                                status_label.set_text("用户创建成功")
                                                ui.notify("用户创建成功", type="positive")
                                                
                                                # 清空输入
                                                username_input.set_value("")
                                                password_input.set_value("")
                                                role_select.set_value("user")
                                                
                                            except Exception as e:
                                                db.rollback()
                                                logging.error(f"创建用户失败: {str(e)}")
                                                status_label.set_text(f"创建用户失败: {str(e)}")
                                                ui.notify("创建用户失败", type="negative")
                                            finally:
                                                db.close()
                                        
                                        with ui.row():
                                            ui.button("创建", on_click=create_user, color="primary")
                                            ui.button("取消", on_click=create_user_dialog.close)
                                    
                                    create_user_dialog.open()
                                
                                ui.button("新增用户", on_click=open_create_user_dialog, icon="add").classes("mb-4")
                                
                                # 用户列表显示
                                user_list_container = ui.column().classes("w-full")
                                
                                # 加载用户列表的函数
                                def load_users():
                                    user_list_container.clear()
                                    db = SessionLocal()
                                    try:
                                        users = db.query(models.User).all()
                                        with user_list_container:
                                            with ui.row().classes("w-full p-2 bg-gray-100 font-bold"):
                                                ui.label("ID").classes("w-16")
                                                ui.label("用户名").classes("flex-1")
                                                ui.label("角色").classes("w-32")
                                                ui.label("操作").classes("w-32")
                                            
                                            for user_item in users:
                                                with ui.row().classes("w-full p-2 border-b"):
                                                    ui.label(str(user_item.id)).classes("w-16")
                                                    ui.label(user_item.username).classes("flex-1")
                                                    ui.label(user_item.role).classes("w-32")
                                                    ui.label("").classes("w-32")  # 占位，未来可以添加编辑/删除功能
                                    except Exception as e:
                                        logging.error(f"加载用户列表失败: {str(e)}")
                                        ui.notify("加载用户列表失败", type="negative")
                                    finally:
                                        db.close()
                                
                                # 初始化加载用户列表
                                load_users()
                        
                        # 角色管理区域
                        with ui.expansion("🔑 角色管理", icon="key").classes("w-full mt-4"):
                            with ui.card().classes("w-full"):
                                # 添加创建角色按钮
                                def open_create_role_dialog():
                                    with ui.dialog() as create_role_dialog, ui.card():
                                        ui.label("创建新角色").classes("text-h6")
                                        
                                        # 角色名输入
                                        role_name_input = ui.input(label="角色名", placeholder="输入角色名").classes("w-full")
                                        
                                        # 权限选择
                                        permissions = {
                                            "questions:read": "查看问题",
                                            "questions:write": "创建/编辑问题",
                                            "questions:delete": "删除问题",
                                            "process:config": "流程配置"
                                        }
                                        
                                        ui.label("权限配置").classes("font-bold mt-4 mb-2")
                                        permission_checkboxes = {}
                                        for perm, desc in permissions.items():
                                            permission_checkboxes[perm] = ui.checkbox(desc, value=False).classes("w-full")
                                        
                                        # 状态标签
                                        status_label = ui.label("").classes("w-full text-center mt-2")
                                        
                                        # 创建角色函数
                                        def create_role():
                                            role_name = role_name_input.value
                                            
                                            # 验证输入
                                            if not role_name:
                                                status_label.set_text("角色名不能为空")
                                                return
                                            
                                            # 获取选中的权限
                                            selected_permissions = [
                                                perm for perm, checkbox in permission_checkboxes.items() 
                                                if checkbox.value
                                            ]
                                            
                                            # 创建角色
                                            db = SessionLocal()
                                            try:
                                                # 检查角色是否已存在
                                                existing_role = db.query(Role).filter(Role.name == role_name).first()
                                                if existing_role:
                                                    status_label.set_text("角色名已存在")
                                                    return
                                                
                                                # 创建新角色
                                                new_role = Role(
                                                    name=role_name,
                                                    permissions=",".join(selected_permissions)
                                                )
                                                db.add(new_role)
                                                db.commit()
                                                db.refresh(new_role)
                                                
                                                status_label.set_text("角色创建成功")
                                                ui.notify("角色创建成功", type="positive")
                                                
                                                # 清空输入
                                                role_name_input.set_value("")
                                                for checkbox in permission_checkboxes.values():
                                                    checkbox.set_value(False)
                                                    
                                            except Exception as e:
                                                db.rollback()
                                                logging.error(f"创建角色失败: {str(e)}")
                                                status_label.set_text(f"创建角色失败: {str(e)}")
                                                ui.notify("创建角色失败", type="negative")
                                            finally:
                                                db.close()
                                        
                                        with ui.row():
                                            ui.button("创建", on_click=create_role, color="primary")
                                            ui.button("取消", on_click=create_role_dialog.close)
                                    
                                    create_role_dialog.open()
                                
                                ui.button("新增角色", on_click=open_create_role_dialog, icon="add").classes("mb-4")
                                
                                # 角色列表显示
                                role_list_container = ui.column().classes("w-full")
                                
                                # 加载角色列表的函数
                                def load_roles():
                                    role_list_container.clear()
                                    db = SessionLocal()
                                    try:
                                        roles = db.query(Role).all()
                                        with role_list_container:
                                            with ui.row().classes("w-full p-2 bg-gray-100 font-bold"):
                                                ui.label("ID").classes("w-16")
                                                ui.label("角色名").classes("flex-1")
                                                ui.label("权限").classes("flex-1")
                                                ui.label("操作").classes("w-32")
                                            
                                            for role in roles:
                                                with ui.row().classes("w-full p-2 border-b"):
                                                    ui.label(str(role.id)).classes("w-16")
                                                    ui.label(role.name).classes("flex-1")
                                                    
                                                    # 显示权限
                                                    permissions = role.get_permissions()
                                                    permissions_display = ", ".join(permissions) if permissions else "无权限"
                                                    ui.label(permissions_display).classes("flex-1")
                                                    
                                                    # 操作按钮占位
                                                    ui.label("").classes("w-32")
                                    except Exception as e:
                                        logging.error(f"加载角色列表失败: {str(e)}")
                                        ui.notify("加载角色列表失败", type="negative")
                                    finally:
                                        db.close()
                                
                                # 初始化加载角色列表
                                load_roles()
                    
                    # 页面加载完成后自动加载问题列表
                    ui.timer(0.1, lambda: asyncio.create_task(load_questions(question_list_container, user)), once=True)
            
    # 未登录时显示提示信息
    else:
        with ui.column().classes("w-full items-center justify-center p-8"):
            ui.label("请登录以查看内容").classes("text-2xl mb-4")
            ui.button("前往登录", on_click=lambda: ui.run_javascript('window.location.href = "/gui/login"')).classes("text-xl p-4")

# 全局变量声明
questions = []  # 用于存储问题列表
question_list_container = None  # 问题列表容器
process_config_dialog = None  # 流程配置对话框
create_dialog = None  # 创建问题对话框

# 异步加载问题列表的函数
async def load_questions(container, user=None):
    """异步加载问题列表"""
    try:
        container.clear()
        with container:
            with ui.row().classes("w-full p-3 bg-gray-100 rounded-lg font-medium"):
                ui.label("ID").classes("w-16 text-center")
                ui.label("问题内容").classes("flex-1")
                ui.label("问题查看").classes("w-24 text-center")
                ui.label("操作").classes("w-32 text-center")
        
        # 调用API获取问题列表
        db = SessionLocal()
        questions = db.query(models.Questions).options(joinedload(models.Questions.choices)).all()
        db.close()
        
        if not questions:
            with container:
                ui.label("暂无问题").classes("w-full text-center text-gray-500 py-8")
            return
        
        # 显示问题列表
        for question in questions:
            with container:
                with ui.card().classes("w-full mb-2 hover:shadow-md transition-shadow"):
                    with ui.card_section().classes("w-full"):
                        with ui.row().classes("w-full items-center"):
                            ui.label(str(question.id)).classes("w-16 text-center")
                            ui.label(question.question_text).classes("flex-1")
                            
                            # 添加查看按钮
                            with ui.row().classes("w-24 justify-center"):
                                def make_view_handler(q=question):
                                    def view_handler():
                                        # 创建一个对话框来显示问题详情
                                        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl"):
                                            ui.label("问题详情").classes("text-xl font-bold mb-4")
                                            ui.label(q.question_text).classes("text-lg mb-4 p-3 bg-gray-50 rounded")
                                            
                                            ui.label("选项：").classes("font-bold mt-4 mb-2")
                                            
                                            # 显示选项
                                            for i, choice in enumerate(q.choices):
                                                with ui.row().classes("w-full items-center mb-2 p-2 hover:bg-gray-50 rounded"):
                                                    # 显示选项字母
                                                    ui.label(chr(65 + i)).classes("font-bold mr-2")  # A, B, C, D...
                                                    
                                                    # 显示选项内容
                                                    ui.label(choice.choice_text).classes("flex-1")
                                                    
                                                    # 显示是否为正确答案
                                                    if choice.is_correct:
                                                        ui.icon("check_circle").classes("text-green-500")
                                                        ui.label("正确答案").classes("text-green-500 ml-2")
                                            
                                            with ui.row().classes("w-full justify-end mt-4"):
                                                ui.button("关闭", on_click=dialog.close)
                                        dialog.open()
                                    return view_handler
                                
                                ui.button("查看", on_click=make_view_handler(), icon="visibility").classes("text-sm")
                            
                            with ui.row().classes("w-32 justify-center"):
                                # 普通用户只能查看，不能删除
                                if user and "questions:delete" in user.get("scopes", []):
                                    def make_delete_handler(question_id):
                                        async def delete_handler():
                                            try:
                                                # 调用API删除问题
                                                db = SessionLocal()
                                                question = db.query(models.Questions).filter(models.Questions.id == question_id).first()
                                                
                                                if not question:
                                                    db.close()
                                                    ui.notify("问题未找到", type="negative")
                                                    return
                                                
                                                # 删除关联的选项
                                                db.query(models.Choices).filter(models.Choices.question_id == question_id).delete()
                                                
                                                # 删除问题
                                                db.delete(question)
                                                db.commit()
                                                db.close()
                                                
                                                ui.notify("问题删除成功", type="positive")
                                                # 重新加载问题列表
                                                asyncio.create_task(load_questions(container, user))
                                            except Exception as e:
                                                db.rollback()
                                                db.close()
                                                logging.error(f"删除问题失败: {str(e)}")
                                                ui.notify(f"删除问题失败: {str(e)}", type="negative")
                                            return delete_handler
                                        
                                        ui.button("🗑️", on_click=make_delete_handler(question.id), 
                                                 color="red").classes("text-sm")
                                else:
                                    ui.label("只读").classes("text-gray-400 text-sm")
    except Exception as e:
        logging.error(f"加载问题列表失败: {str(e)}")
        logging.error(f"详细错误信息: {traceback.format_exc()}")
        with container:
            ui.label(f"加载失败: {str(e)}").classes("w-full text-center text-red-500 py-4")

async def load_process_config():
    """从数据库加载流程配置"""
    try:
        db = SessionLocal()
        process_steps = db.query(models.ProcessStep).order_by(models.ProcessStep.step_index).all()
        db.close()
        
        return process_steps
    except Exception as e:
        logging.error(f"加载流程配置失败: {str(e)}")
        return []

# 存储用户会话，现在包括scopes
user_sessions = {}

# 初始化数据库用户（如果不存在）
def init_users(db: Session):
    # 检查是否已有用户
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        # 创建管理员用户，具有所有权限
        admin_user = User(username="admin", role="administrator")
        admin_user.set_password("admin")  # 使用更短的密码
        db.add(admin_user)
        
        # 创建普通用户，只有基本权限
        regular_user = User(username="user", role="user")
        regular_user.set_password("user")  # 使用更短的密码
        db.add(regular_user)
        
        db.commit()
        logging.info("已创建初始用户: admin和user")
    else:
        logging.info("用户已存在，跳过初始化")
    
    # 检查是否已有角色
    admin_role = db.query(Role).filter(Role.name == "administrator").first()
    if not admin_role:
        # 创建管理员角色
        admin_role = Role(
            name="administrator",
            permissions="questions:read,questions:write,questions:delete,process:config"
        )
        db.add(admin_role)
        
        # 创建普通用户角色
        user_role = Role(name="user", permissions="questions:read")
        db.add(user_role)
        
        db.commit()
        logging.info("已创建初始角色: administrator和user")
    else:
        logging.info("角色已存在，跳过初始化")

# 数据库依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

# 认证相关函数
def get_current_user(request: Request):
    """验证用户是否已登录"""
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 从数据库获取会话信息
    db = SessionLocal()
    try:
        session = db.query(UserSession).filter(UserSession.session_token == token).first()
        if not session:
            raise HTTPException(status_code=401, detail="会话无效")
        
        # 将数据库会话对象转换为字典
        user_session = {
            "username": session.username,
            "role": session.role,
            "scopes": session.scopes.split(",") if session.scopes else []
        }
        return user_session
    finally:
        db.close()

async def get_current_active_user(
    security_scopes: SecurityScopes, 
    request: Request
):
    """验证用户是否有足够的权限执行操作"""
    user_session = get_current_user(request)
    
    if not security_scopes.scopes:
        return user_session
    
    # 检查用户是否有足够的权限
    user_scopes = user_session.get("scopes", [])
    for scope in security_scopes.scopes:
        if scope not in user_scopes:
            raise HTTPException(
                status_code=403,
                detail="权限不足",
                headers={"WWW-Authenticate": f"Bearer scope={security_scopes.scope_str}"},
            )
    return user_session

# API路由
# 验证用户
from typing import Union
async def verify_user(db: Session, username: str, password: str) -> Union[User, None]:
    user = db.query(User).filter(User.username == username).first()
    if user and user.verify_password(password):
        return user
    return None

@app.post("/api/login")
async def login_api(username: str = Form(...), password: str = Form(...), db: db_dependency = None):
    """API登录接口"""
    user = await verify_user(db, username, password)
    if not user:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    
    # 根据用户角色从数据库获取权限范围
    role_record = db.query(Role).filter(Role.name == user.role).first()
    scopes = []
    if role_record:
        scopes = role_record.get_permissions()
    else:
        # 兼容旧的角色处理方式
        if user.role == "administrator":
            scopes = ["questions:read", "questions:write", "questions:delete", "process:config"]
        elif user.role == "user":
            scopes = ["questions:read"]
    
    session_token = secrets.token_urlsafe(16)
    
    # 将会话信息存储到数据库
    db = SessionLocal()
    try:
        user_session = UserSession(
            session_token=session_token,
            username=user.username,
            role=user.role,
            scopes=",".join(scopes)
        )
        db.add(user_session)
        db.commit()
    finally:
        db.close()
    
    response = JSONResponse({
        "success": True,
        "message": "登录成功",
        "user": {
            "username": user.username,
            "role": user.role
        },
        "scopes": scopes
    })
    response.set_cookie(
        key="session_token", 
        value=session_token, 
        httponly=True, 
        max_age=3600,
        samesite="lax",
        path="/gui"
    )
    return response

@app.get("/api/logout")
async def logout_api(request: Request, db: db_dependency = None):
    """API登出接口 - 登出后重定向到登录页面"""
    token = request.cookies.get("session_token")
    if token:
        # 从数据库中删除会话信息
        session = db.query(UserSession).filter(UserSession.session_token == token).first()
        if session:
            db.delete(session)
            db.commit()
    
    # 使用重定向响应替代JSON响应
    response = RedirectResponse(url="/gui/login")
    response.delete_cookie(key="session_token")
    return response

# NiceGUI页面 - 完全重写的登录页面，避免任何重定向
# 注意：由于NiceGUI挂载在/gui路径下，这里只需要定义为/login，实际访问路径为/gui/login
@ui.page("/login")
def login_page(request: Request):
    """登录页面 - 完全独立，不包含任何重定向逻辑"""
    # 简化UI设计
    ui.add_head_html("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    ui.query(".nicegui-content").classes("flex flex-col items-center justify-center h-screen p-6")
    
    # 创建简单的登录表单容器
    login_container = ui.card().classes("w-full max-w-md p-6")
    
    with login_container:
        ui.label("🔐 登录系统").classes("text-2xl font-bold mb-6 text-center")
        
        username_input = ui.input("用户名", placeholder="请输入用户名").classes("w-full mb-4")
        password_input = ui.input("密码", placeholder="请输入密码", password=True).classes("w-full mb-4")
        
        status_label = ui.label("").classes("w-full mb-4 text-center")
        
        async def handle_login():
            username = username_input.value or ""
            password = password_input.value or ""
            
            if not username:
                status_label.text = "请输入用户名"
                return
            
            if not password:
                status_label.text = "请输入密码"
                return
            
            status_label.text = "正在登录..."
            
            try:
                # 直接验证用户
                db = SessionLocal()
                user = await verify_user(db, username, password)
                db.close()
                
                if user:
                    # 根据用户角色定义权限范围
                    scopes = []
                    if user.role == "administrator":
                        scopes = ["questions:read", "questions:write", "questions:delete", "process:config"]
                    elif user.role == "user":
                        scopes = ["questions:read"]
                    
                    session_token = secrets.token_urlsafe(16)
                    
                    # 将会话信息存储到数据库
                    db = SessionLocal()
                    try:
                        user_session = UserSession(
                            session_token=session_token,
                            username=user.username,
                            role=user.role,
                            scopes=",".join(scopes)
                        )
                        db.add(user_session)
                        db.commit()
                    finally:
                        db.close()
                    
                    # 先清除旧的 session_token cookie，再设置新的
                    js_code = f"""
                    document.cookie = "session_token=; path=/gui; expires=Thu, 01 Jan 1970 00:00:00 GMT";
                    document.cookie = "session_token={session_token}; path=/gui; SameSite=Lax";
                    window.location.href = "/gui/";
                    """
                    ui.run_javascript(js_code)
                else:
                    status_label.text = "用户名或密码错误"
            except Exception as e:
                status_label.text = f"登录错误: {str(e)}"
        
        ui.button("登录", on_click=handle_login).classes("w-full")
    
    # 简单的测试账户信息
    ui.separator().classes("my-4 w-full max-w-md")
    ui.label("测试账户信息:").classes("font-bold")
    ui.label("管理员: admin / admin")
    ui.label("普通用户: user / user")

# 移除登录重定向路由，避免任何可能的重定向循环
# 让用户直接访问/gui/login

# 将NiceGUI集成到FastAPI应用 - 修复前端资源加载问题
# 将NiceGUI集成到FastAPI应用 - 修复WebSocket连接问题
ui.run_with(
    app,
    mount_path="/gui",
    title="登录系统",
    dark=False,
    tailwind=True,
    show_welcome_message=False,
)

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)