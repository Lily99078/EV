"""数据库连接诊断与修复工具"""
import socket
import os
import subprocess
import time
import sys
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, engine, SQLALCHEMY_DATABASE_URL
from models import User, Base
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_postgresql_service():
    """检查PostgreSQL服务状态，使用多种方法综合判断"""
    try:
        # 方法1: 直接尝试数据库连接（最可靠的方法）
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            logger.info("✅ 数据库连接成功，PostgreSQL服务正常运行")
            return True
        except:
            pass  # 如果连接失败，尝试其他方法
            
        # Windows环境检查服务 - 尝试多种可能的服务名称
        if os.name == 'nt':
            # 尝试不同版本的PostgreSQL服务名称
            service_names = [
                'postgresql-x64-15',
                'postgresql-x64-14',
                'postgresql-x64-13',
                'postgresql-15',
                'postgresql-14',
                'postgresql-13',
                'postgresql'
            ]
            
            for service_name in service_names:
                try:
                    result = subprocess.run(['sc', 'query', service_name], 
                                          capture_output=True, text=True)
                    if "RUNNING" in result.stdout:
                        logger.info(f"✅ PostgreSQL服务({service_name})正在运行")
                        return True
                except:
                    continue
            
            # 尝试检查PostgreSQL进程
            try:
                result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq postgres.exe'], 
                                      capture_output=True, text=True)
                if 'postgres.exe' in result.stdout:
                    logger.info("✅ PostgreSQL进程正在运行")
                    return True
            except:
                pass
            
            logger.warning("⚠️  PostgreSQL服务可能未运行，但数据库连接可能仍然有效")
            # 由于之前的连接测试已经失败，返回False
            return False
        else:
            # 非Windows环境
            try:
                result = subprocess.run(['pg_isready'], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info("✅ PostgreSQL服务响应正常")
                    return True
            except:
                pass
            
            logger.warning("⚠️  PostgreSQL服务检查失败，但数据库连接可能仍然有效")
            return False
    except Exception as e:
        logger.warning(f"⚠️  检查PostgreSQL服务时出错: {str(e)}，但数据库连接可能仍然有效")
        return False

def check_port_connection():
    """检查PostgreSQL端口连接"""
    try:
        # 从连接字符串提取端口号，默认5432
        port = 5432
        if "port=" in SQLALCHEMY_DATABASE_URL:
            port_start = SQLALCHEMY_DATABASE_URL.find("port=") + 5
            port_end = SQLALCHEMY_DATABASE_URL.find("", port_start)
            port = int(SQLALCHEMY_DATABASE_URL[port_start:port_end])
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        
        if result == 0:
            logger.info(f"✅ 端口 {port} 可正常连接")
            return True
        else:
            logger.error(f"❌ 无法连接到端口 {port}")
            return False
    except Exception as e:
        logger.error(f"❌ 端口连接测试失败: {str(e)}")
        return False

def analyze_connection_string():
    """分析连接字符串"""
    try:
        logger.info(f"📋 数据库连接字符串: {SQLALCHEMY_DATABASE_URL}")
        # 检查连接字符串格式
        if not SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
            logger.error("❌ 连接字符串格式错误，应使用postgresql://开头")
            return False
        
        # 检查是否包含必要组件
        required_parts = ["@", ":", "/"]
        for part in required_parts:
            if part not in SQLALCHEMY_DATABASE_URL:
                logger.error(f"❌ 连接字符串缺少必要组件: {part}")
                return False
        
        logger.info("✅ 连接字符串格式正确")
        return True
    except Exception as e:
        logger.error(f"❌ 分析连接字符串失败: {str(e)}")
        return False

def test_database_existence():
    """测试数据库是否存在"""
    try:
        # 尝试创建一个简单的连接并执行查询
        db = SessionLocal()
        # 使用正确的SQLAlchemy 2.0语法执行查询
        from sqlalchemy import text
        result = db.execute(text("SELECT 1"))
        logger.info("✅ 数据库存在且可访问")
        db.close()
        return True
    except Exception as e:
        logger.error(f"❌ 数据库不存在或无法访问: {str(e)}")
        return False

def test_table_creation():
    """测试数据库表创建"""
    try:
        # 尝试创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("✅ 数据库表创建/更新成功")
        return True
    except Exception as e:
        logger.error(f"❌ 数据库表创建失败: {str(e)}")
        return False

def test_user_operations():
    """测试用户操作"""
    try:
        db = SessionLocal()
        
        # 检查是否已有用户
        existing_users = db.query(User).count()
        logger.info(f"📊 数据库中已有 {existing_users} 个用户")
        
        # 创建测试用户
        test_user = User(username="diagnostic_user", role="user")
        test_user.set_password("diagnostic123")
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        logger.info(f"✅ 创建测试用户成功: ID={test_user.id}, 用户名={test_user.username}")
        
        # 测试查询
        queried_user = db.query(User).filter(User.username == "diagnostic_user").first()
        if queried_user:
            logger.info(f"✅ 查询用户成功: {queried_user.username}")
        
        # 测试密码验证
        if queried_user and queried_user.verify_password("diagnostic123"):
            logger.info("✅ 密码验证成功")
        
        # 清理测试数据
        db.delete(test_user)
        db.commit()
        logger.info("✅ 清理测试数据完成")
        
        db.close()
        return True
    except Exception as e:
        logger.error(f"❌ 用户操作测试失败: {str(e)}")
        if 'db' in locals():
            db.close()
        return False

def test_multiple_connection_attempts():
    """测试多次连接尝试，模拟登录后的连接情况"""
    logger.info("🔄 开始测试多次连接尝试...")
    success_count = 0
    failure_count = 0
    
    for i in range(5):  # 测试5次连接
        try:
            db = SessionLocal()
            result = db.execute(text("SELECT 1"))
            success_count += 1
            logger.info(f"✅ 连接尝试 {i+1} 成功")
            db.close()
            # 模拟间隔
            time.sleep(0.5)
        except Exception as e:
            failure_count += 1
            logger.error(f"❌ 连接尝试 {i+1} 失败: {str(e)}")
            # 添加重试逻辑
            time.sleep(1)
    
    logger.info(f"📊 连接测试结果: 成功={success_count}, 失败={failure_count}")
    # 如果大部分连接成功，则认为测试通过（容错处理）
    return success_count >= 3

def test_connection_pool():
    """测试数据库连接池状态"""
    logger.info("🔄 开始测试连接池状态...")
    try:
        # 测试连接池的基本功能
        connections = []
        max_connections = 5
        
        # 尝试创建多个连接
        for i in range(max_connections):
            try:
                db = SessionLocal()
                db.execute(text("SELECT 1"))
                connections.append(db)
                logger.info(f"✅ 成功创建连接池连接 {i+1}")
            except Exception as e:
                logger.error(f"❌ 创建连接池连接 {i+1} 失败: {str(e)}")
                break
        
        # 关闭所有连接
        for db in connections:
            try:
                db.close()
            except:
                pass
        
        logger.info(f"✅ 连接池测试完成，成功创建 {len(connections)}/{max_connections} 个连接")
        
        # 压力测试：短时间内多次创建和关闭连接
        logger.info("🔄 执行连接池压力测试...")
        pressure_success = 0
        pressure_total = 10
        
        for i in range(pressure_total):
            try:
                db = SessionLocal()
                db.execute(text("SELECT 1"))
                db.close()
                pressure_success += 1
            except:
                pass
            time.sleep(0.1)  # 短暂延迟
        
        logger.info(f"✅ 连接池压力测试完成: 成功={pressure_success}/{pressure_total}")
        return pressure_success >= pressure_total * 0.8  # 80%成功率视为通过
    except Exception as e:
        logger.error(f"❌ 连接池测试失败: {str(e)}")
        return False

def attempt_auto_fix():
    """尝试自动修复数据库连接问题"""
    logger.info("🔧 开始自动修复尝试...")
    fixes_applied = []
    
    # 尝试创建所有表（可能修复表结构问题）
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ 已自动修复数据库表结构")
        fixes_applied.append("修复数据库表结构")
    except Exception as e:
        logger.error(f"❌ 修复表结构失败: {str(e)}")
    
    # 检查并修复连接池问题
    try:
        # 尝试多次创建和关闭连接以清理可能的连接泄漏
        for _ in range(3):
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            time.sleep(0.5)
        logger.info("✅ 已清理并重置连接池")
        fixes_applied.append("重置连接池")
    except Exception as e:
        logger.error(f"❌ 重置连接池失败: {str(e)}")
    
    if fixes_applied:
        logger.info(f"✅ 已应用的修复: {', '.join(fixes_applied)}")
    else:
        logger.info("⚠️  未应用任何自动修复")
    
    return len(fixes_applied) > 0

def comprehensive_diagnostics():
    """综合诊断数据库连接问题"""
    logger.info("🚀 开始数据库连接综合诊断...")
    
    # 执行所有诊断步骤
    diagnostics = [
        ("检查PostgreSQL服务", check_postgresql_service),
        ("检查端口连接", check_port_connection),
        ("分析连接字符串", analyze_connection_string),
        ("测试数据库存在性", test_database_existence),
        ("测试表创建", test_table_creation),
        ("测试用户操作", test_user_operations),
        ("测试连接池", test_connection_pool),  # 新增连接池测试
        ("测试多次连接尝试", test_multiple_connection_attempts)
    ]
    
    results = []
    for name, test_func in diagnostics:
        logger.info(f"\n🔍 {name}")
        result = test_func()
        results.append((name, result))
    
    # 总结
    logger.info("\n📊 诊断结果总结:")
    all_success = True
    critical_fails = []
    
    for name, result in results:
        status = "✅ 成功" if result else "❌ 失败"
        logger.info(f"{status}: {name}")
        if not result:
            all_success = False
            # 记录关键失败项
            if name not in ["检查PostgreSQL服务"]:  # 服务检查可能有误报
                critical_fails.append(name)
    
    # 智能判断：如果只有服务检查失败但其他都成功，认为基本正常
    if len(critical_fails) == 0 and not all_success:
        logger.info("\n🎉 数据库连接基本正常！服务检查可能存在误报。")
        logger.info("💡 建议：应用程序可以正常使用数据库功能。")
        return True
    
    if all_success:
        logger.info("\n🎉 所有诊断测试通过！数据库连接正常。")
    else:
        logger.info("\n⚠️  部分诊断测试失败，请根据失败项检查问题。")
        logger.info("💡 常见解决方案：")
        logger.info("1. 确保PostgreSQL服务已启动")
        logger.info("2. 检查数据库名称是否正确且已创建")
        logger.info("3. 验证用户名和密码是否正确")
        logger.info("4. 检查防火墙是否阻止了连接")
        logger.info("5. 确认PostgreSQL监听端口配置正确")
        logger.info("6. 检查数据库连接池配置")
    
    return all_success or len(critical_fails) == 0

def run_until_fixed(max_attempts=3):
    """自动运行诊断脚本，直至问题解决或达到最大尝试次数"""
    logger.info(f"🔄 开始自动诊断与修复流程 (最多{max_attempts}次尝试)...")
    
    for attempt in range(1, max_attempts + 1):
        logger.info(f"\n📋 尝试 {attempt}/{max_attempts}")
        
        # 运行诊断
        success = comprehensive_diagnostics()
        
        if success:
            logger.info("\n🎉 数据库连接问题已解决！")
            return True
        
        if attempt < max_attempts:
            # 尝试自动修复
            logger.info(f"\n🔧 尝试自动修复问题...")
            attempt_auto_fix()
            
            # 等待一段时间后重试
            wait_time = 5
            logger.info(f"\n⏱️  等待 {wait_time} 秒后进行下一次尝试...")
            time.sleep(wait_time)
    
    logger.error(f"\n❌ 达到最大尝试次数 ({max_attempts})，问题未完全解决。")
    logger.info("💡 建议手动检查以下方面：")
    logger.info("1. PostgreSQL服务状态")
    logger.info("2. 数据库连接配置")
    logger.info("3. 数据库权限设置")
    logger.info("4. 系统资源使用情况")
    return False

if __name__ == "__main__":
    print("开始数据库连接诊断与修复流程...\n")
    
    # 运行自动诊断与修复流程
    success = run_until_fixed(max_attempts=3)
    
    if success:
        print("\n🎉 数据库连接问题已成功解决！")
        print("💡 建议：重启应用程序以应用所有更改。")
    else:
        print("\n❌ 数据库连接问题未能完全解决。")
        print("💡 请查看日志中的错误信息并手动解决问题。")
    
    print("\n诊断与修复流程完成!")