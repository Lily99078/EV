from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from urllib.parse import quote_plus  # 导入编码函数
from base import Base  # 从基础模块导入

# 原始密码
password = "Huiteng888"

# 对密码进行URL编码
encoded_password = quote_plus(password)
# 替换为你自己的数据库信息：用户名、密码、主机、端口、数据库名
SQLALCHEMY_DATABASE_URL = f'postgresql://postgres:{encoded_password}@localhost:5432/QuizApplicationYT'

# 创建引擎
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 创建配置好的 SessionLocal 类，每个请求将使用一个独立的会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



