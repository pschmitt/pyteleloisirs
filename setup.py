from setuptools import find_packages, setup


setup(
    name='pyteleloisirs',
    version='1.1',
    license='GPL3',
    description='Get TV program data from teleloisir',
    long_description=open('README.rst').read(),
    author='Philipp Schmitt',
    author_email='philipp@schmitt.co',
    url='https://github.com/pschmitt/pyteleloisir',
    packages=find_packages(),
    install_requires=['requests', 'bs4'],
)
