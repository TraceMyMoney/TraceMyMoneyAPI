import importlib
import os

ROUTE_LIST = []

for file in os.listdir(os.path.dirname(__file__)):
    mod_name = file[:-3]
    if "." not in file:
        continue

    module = importlib.import_module(
        ".".join(os.path.relpath(__file__).split("/")[:-1]) + "." + mod_name
    )
    url = getattr(module, "urls", None)
    if url:
        ROUTE_LIST.extend(url)
