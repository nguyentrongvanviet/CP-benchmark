from cpbench.generators import generate as _generate, validate as _validate

def generate(seed, count):
    return _generate("4A", seed, count)

def validate(text):
    return _validate("4A", text)
