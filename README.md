# Ev 项目

这是一个基于 FastAPI 和 NiceGUI 构建的 Python Web 应用项目，提供现代化的 API 接口与交互式前端界面。

## 技术栈

- 后端: FastAPI==0.121.1（异步框架）
- 前端: NiceGUI==3.2.0（Python 原生 GUI 框架）
- 数据库: PostgreSQL（通过 psycopg2-binary==2.9.11 驱动连接）
- ORM: SQLAlchemy==2.0.44
- 数据验证: Pydantic==2.12.4（v2 版本）
- 数据库迁移: Alembic==1.13.1
- 文件上传支持: python-multipart==0.0.20
- 服务器: uvicorn==0.38.0（ASGI 服务器）

## Docker 部署

项目支持通过 Docker 进行容器化部署，可以快速在任何支持 Docker 的环境中运行。

### 使用 Docker 直接部署

构建并运行容器：

```bash
# 构建镜像
docker build -t ev-app .

# 运行容器
docker run -p 8001:8001 ev-app
```

### 使用 Docker Compose 部署（推荐）

使用 docker-compose 可以同时启动应用和数据库服务：

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 停止所有服务
docker-compose down
```

### 环境变量配置

可以通过环境变量配置数据库连接和其他参数：

- `DB_USER`: 数据库用户名 (默认: postgres)
- `DB_PASSWORD`: 数据库密码 (默认: Huiteng888)
- `DB_HOST`: 数据库主机地址 (默认: db)
- `DB_PORT`: 数据库端口 (默认: 5432)
- `DB_NAME`: 数据库名称 (默认: QuizApplicationYT)

在 docker-compose.yml 中修改这些环境变量以适应你的部署环境。

## 本地开发

### 环境搭建

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境（Windows）
venv\Scripts\activate

# 或 Linux/macOS
# source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
```

### 启动应用

```bash
# 启动 FastAPI/NiceGUI 服务
uvicorn main:app --reload
```

访问地址: http://localhost:8000

## 生产部署

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4
```