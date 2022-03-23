from setuptools import setup, find_namespace_packages

with open('README.md', 'r') as readme:
    long_description = readme.read()

exec(open('dmod/dataservice/_version.py').read())

setup(
    name='dmod-dataservice',
    version=__version__,
    description='',
    long_description=long_description,
    author='',
    author_email='',
    url='',
    license='',
    install_requires=['dmod-communication>=0.5.0', 'dmod-scheduler>=0.5.0', 'redis'],
    packages=find_namespace_packages(exclude=('tests', 'test', 'deprecated', 'conf', 'schemas', 'ssl', 'src'))
)