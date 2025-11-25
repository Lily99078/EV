# 电池管理系统

基于 FastAPI 和 NiceGUI 构建的电池管理系统，提供现代化的 Web 界面用于管理电池测试流程和问题库。

## 功能特性

- 用户认证和权限管理
- 电池测试流程配置
- 问题库管理（创建、查看、删除问题）
- 基于 OAuth2 Scopes 的细粒度权限控制

## 技术栈

- 后端: FastAPI
- 前端: NiceGUI
- 数据库: SQLAlchemy + PostgreSQL
- 认证: OAuth2 Scopes

## 安装和运行

1. 克隆项目:
   ```
   git clone <your-repo-url>
   ```

2. 创建虚拟环境:
   ```
   python -m venv venv
   ```

3. 激活虚拟环境:
   ```
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

4. 安装依赖:
   ```
   pip install -r requirements.txt
   ```

5. 运行应用:
   ```
   uvicorn main:app --reload
   ```

## 使用说明

- 默认管理员账户: admin / admin
- 默认用户账户: user / user

## 许可证

MIT