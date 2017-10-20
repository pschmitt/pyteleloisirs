from setuptools import find_packages, setup


setup(
    name='pyteleloisirs',
    version='2.0',
    license='GPL3',
    description='Get TV program data from teleloisirs',
    long_description=open('README.rst').read(),
    author='Philipp Schmitt',
    author_email='philipp@schmitt.co',
    url='https://github.com/pschmitt/pyteleloisirs',
    packages=find_packages(),
    install_requires=['requests', 'bs4'],
)
