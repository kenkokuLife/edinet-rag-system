"""
全局应用状态管理模块
用于存储应用级别的共享状态
"""

# 全局应用状态
app_state = {}

def get_app_state():
    """获取应用状态"""
    return app_state

def set_app_state(key: str, value):
    """设置应用状态"""
    app_state[key] = value

def get_component(component_name: str):
    """获取特定组件"""
    return app_state.get(component_name)

def set_component(component_name: str, component):
    """设置特定组件"""
    app_state[component_name] = component
