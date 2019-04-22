from make_it_so import md5, yaml_config


def test_md5():
    assert md5("templates/test.php") == "4d200d0d8776fc1a45f611b16cfa4735"

def test_yaml_config():
    assert yaml_config("node_config.yaml") == {'application': [{'add_package': ['php5', 'libapache2-mod-php5', 'php5-mcrypt'], 'ensure': 'install', 'name': 'apache2'}], 'password': 'blah', 'username': 'root'}

