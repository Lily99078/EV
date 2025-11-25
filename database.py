import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus  # 导入编码函数
from base import Base  # 从基础模块导入
import models  # 导入所有模型以确保Role被包含在元数据中

# 从环境变量获取数据库配置，如果未设置则使用默认值
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'Huiteng888')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'QuizApplicationYT')

# 对密码进行URL编码
encoded_password = quote_plus(DB_PASSWORD)
SQLALCHEMY_DATABASE_URL = f'postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

# 创建引擎
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 创建配置好的 SessionLocal 类，每个请求将使用一个独立的会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)