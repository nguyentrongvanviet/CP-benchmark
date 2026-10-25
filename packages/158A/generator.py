from cpbench.generators import generate as _generate, validate as _validate

def generate(seed, count):
    return _generate("158A", seed, count)

def validate(text):
    return _validate("158A", text)
