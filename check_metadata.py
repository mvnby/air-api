from sqlmodel import SQLModel
from models import *
print("Registered tables:", SQLModel.metadata.tables.keys())
