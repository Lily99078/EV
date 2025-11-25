from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from base import Base  # 从基础模块导入
from werkzeug.security import generate_password_hash, check_password_hash

class Questions(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(String, unique=True, index=True)  
    
    choices = relationship("Choices", back_populates="question", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Question(id={self.id}, text='{self.question_text}')>"

class Choices(Base):
    __tablename__ = "choices"
    
    id = Column(Integer, primary_key=True, index=True)
    choice_text = Column(String, index=True)
    is_correct = Column(Boolean, default=False)
    question_id = Column(Integer, ForeignKey('questions.id'))
    
    question = relationship("Questions", back_populates="choices")
    
    def __repr__(self):
        return f"<Choice(id={self.id}, text='{self.choice_text}', correct={self.is_correct})>"


class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    # 权限以逗号分隔的形式存储
    permissions = Column(String, nullable=False)
    
    def __repr__(self):
        return f"<Role(id={self.id}, name='{self.name}')>"
    
    def get_permissions(self):
        """获取角色的所有权限列表"""
        if self.permissions:
            return self.permissions.split(',')
        return []
    
    def add_permission(self, permission):
        """为角色添加权限"""
        perms = self.get_permissions()
        if permission not in perms:
            perms.append(permission)
            self.permissions = ','.join(perms)
    
    def remove_permission(self, permission):
        """为角色移除权限"""
        perms = self.get_permissions()
        if permission in perms:
            perms.remove(permission)
            self.permissions = ','.join(perms)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="user")
    
    def set_password(self, password):
        """设置密码（加密）"""
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        """验证密码"""
        print(f"[密码验证断点] 用户:{self.username}, 输入密码:{password}, 存储的哈希值前20位:{self.password_hash[:20]}...")
        result = check_password_hash(self.password_hash, password)
        print(f"[密码验证断点] 验证结果: {result}")
        return result
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    role = Column(String, nullable=False)
    scopes = Column(String)  # 以逗号分隔的权限范围列表
    
    def __repr__(self):
        return f"<UserSession(id={self.id}, username='{self.username}', role='{self.role}')>"


class Batteries(Base):
    __tablename__ = "batteries"
    
    batteries_id = Column(Integer, primary_key=True, index=True)
    batteries_name = Column(String, unique=True, index=True, nullable=False)
    batteries_capacity = Column(Integer, nullable=False)
    
    def __repr__(self):
        return f"<Battery(id={self.batteries_id}, name='{self.batteries_name}', capacity={self.batteries_capacity})>"


class ProcessStep(Base):
    __tablename__ = "process_steps"
    
    id = Column(Integer, primary_key=True, index=True)
    step_index = Column(Integer, nullable=False)
    step_type = Column(String, nullable=False)  # CC-CV, CC, DC, Rest, END
    current = Column(Float, nullable=True)
    voltage = Column(Float, nullable=True)
    end_current = Column(Float, nullable=True)
    step_time = Column(String, nullable=True)  # HH:MM:SS格式
    capacity_check = Column(Boolean, default=False)
    temp_compensation = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<ProcessStep(id={self.id}, index={self.step_index}, type='{self.step_type}')>"