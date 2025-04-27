import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access the variables
database_url = os.getenv("DATABASE_URL")
secret_key = os.getenv("SECRET_KEY")
debug_mode = os.getenv("DEBUG")

# Print values (for debugging)
print(f"Database URL: {database_url}")
print(f"Secret Key: {secret_key}")
print(f"Debug Mode: {debug_mode}")
