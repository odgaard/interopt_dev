# setup.py
from setuptools import setup, find_packages

setup(
    name='interopt',
    version='0.1.3',
    author='Jacob Odgård Tørring',
    author_email='jacob.torring@ntnu.no',
    packages=find_packages(),
    license='LICENSE',
    description='An interoperability layer for black-box optimization',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    install_requires=[
        'requests',
        'pandas',
        'catboost',
        'grpcio',
        'grpcio-tools',
        'protobuf',
        'scikit-learn',
        'pydantic'
    ],
)
