from setuptools import setup, find_packages

setup(
    name="devagent",
    version="0.1.0",
    description="Autonomous software engineering agent powered by Cerebras",
    python_requires=">=3.11",
    packages=find_packages(),
    install_requires=[
        "cerebras-cloud-sdk>=1.0.0",
        "langgraph>=0.2.0",
        "langchain-core>=0.3.0",
        "langchain-openai>=0.2.0",
        "PyGithub>=2.1.1",
        "GitPython>=3.1.40",
        "typer>=0.12.0",
        "rich>=13.7.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.5.0",
        "tenacity>=8.2.3",
    ],
    entry_points={
        "console_scripts": [
            "devagent=main:app_cli",
        ],
    },
)
