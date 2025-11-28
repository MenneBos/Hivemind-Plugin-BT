from setuptools import setup, find_packages
from os import path

PLUGIN_TYPE = "ovos.plugin.phal"  # Adjust based on the plugin type
PLUGIN_NAME = "Hivemind-Plugin-BT"
PLUGIN_PKG = PLUGIN_NAME.replace("-", "_")
PLUGIN_CLAZZ = "GPIOInputs" # same is class name in __init__.py
PLUGIN_CONFIGS = "MyPluginConfig"

BASE_PATH = path.abspath(path.dirname(__file__))

PLUGIN_ENTRY_POINT = f'{PLUGIN_NAME} = {PLUGIN_PKG}:{PLUGIN_CLAZZ}'
CONFIG_ENTRY_POINT = f'{PLUGIN_NAME}.config = {PLUGIN_PKG}:{PLUGIN_CONFIGS}'

def get_requirements(requirements_filename: str):
    requirements_file = path.join(BASE_PATH, "requirements",
                                  requirements_filename)
    with open(requirements_file, 'r', encoding='utf-8') as r:
        requirements = r.readlines()
    requirements = [r.strip() for r in requirements if r.strip() and
                    not r.strip().startswith("#")]
    return requirements

setup(
    name=PLUGIN_NAME,
    version='0.1.0',
    packages=find_packages(),
    install_requires=get_requirements('requirements.txt'),
    keywords='ovos hivemind plugin phal bluetooth',
    entry_points={PLUGIN_TYPE: PLUGIN_ENTRY_POINT, f'{PLUGIN_TYPE}.config': CONFIG_ENTRY_POINT}
)

