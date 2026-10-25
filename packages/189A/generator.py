from cpbench.generators import generate as _generate, validate as _validate

def generate(seed, count):
    return _generate("189A", seed, count)

def validate(text):
    return _validate("189A", text)
