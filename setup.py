from setuptools import setup

setup(
    name='bt_ccxt_store',
    version='2023.01.30',
    description='A fork of Ed Bartosh\'s CCXT Store Work with some additions',
    url='https://github.com/viper7882/bt-ccxt-store',
    author='Dave Vallance',
    author_email='dave@backtest-rookies.com',
    license='MIT',
    packages=['ccxtbt'],
    install_requires=['backtrader', 'ccxt', 'pandas', 'numpy'],
)
