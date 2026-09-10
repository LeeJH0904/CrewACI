from setuptools import setup, find_packages

setup(
    name="aciarena",
    version="0.1",
    # G3's official CrewAI reference harness is intentionally run from the
    # repository in an isolated environment, not shipped with ACIArena.
    packages=find_packages(exclude=("native_reference", "native_reference.*")),
    install_requires=[
        "openai==1.63.2",
        "pydantic==2.10.6",
        "tenacity==9.0.0",
        "PyYAML==6.0.2",
        "datasets==3.6.0",
        "math-verify==0.6.0",
        "human_eval==1.0.3",
        "colorlog==6.9.0",
        "transformers==4.56.1",
    ],
)
