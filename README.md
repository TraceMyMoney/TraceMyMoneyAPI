# Stalk My Money API

A production-ready FastAPI backend for expense tracking and financial management. Converted from Flask "TraceMyMoney" to FastAPI with improvements.

## 🚀 Features

- ✅ **User Authentication** - JWT-based authentication
- ✅ **Bank Management** - Create, manage multiple bank accounts
- ✅ **Expense Tracking** - Track expenses with detailed entries
- ✅ **Entry Tags** - Categorize expenses with custom tags
- ✅ **Advanced Search** - Search by tags, keywords, date ranges, banks
- ✅ **Analytics** - Aggregated data by tags for visualization
- ✅ **User Preferences** - Customizable settings (page size, dark mode, privacy)
- ✅ **MongoDB** - Async MongoDB with Motor driver
- ✅ **Type Safety** - Full type hints with Pydantic validation
- ✅ **Auto Documentation** - Swagger UI and ReDoc

## 📊 Tech Stack

- **FastAPI** - Modern async web framework
- **MongoDB** - NoSQL database with Motor (async driver)
- **Pydantic** - Data validation
- **JWT** - Secure authentication
- **Argon2** - Password hashing
- **Docker** - Containerization

## 🏗️ Project Structure

```
stalk-my-money-api/
├── app/
│   ├── api/
│   │   ├── deps.py              # Dependencies (auth, db)
│   │   └── v1/
│   │       ├── api.py           # Router aggregator
│   │       └── endpoints/       # API endpoints
│   ├── core/
│   │   ├── config.py            # Settings
│   │   └── security.py          # JWT & password hashing
│   ├── db/
│   │   └── session.py           # MongoDB connection
│   ├── models/                  # MongoDB document models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/                # Business logic
│   ├── utils/                   # Utility functions
│   └── main.py                  # FastAPI application
├── tests/                       # Test files
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🔧 Installation

### Prerequisites

- Python 3.11+
- MongoDB 7.0+
- Docker & Docker Compose (optional)

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd stalk-my-money-api
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and update:

- Generate `SECRET_KEY`: `openssl rand -hex 32`
- Update MongoDB connection if needed

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 🚀 Running the Application

### Option 1: Using Docker (Recommended)

```bash
# Start MongoDB and API
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Option 2: Local Development

Make sure MongoDB is running, then:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## 📚 API Documentation

Once running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/api/v1/openapi.json

## 🔐 API Endpoints

### Authentication

- `POST /api/v1/login` - Login (get JWT token)
- `POST /api/v1/register` - Register new user

### Banks

- `GET /api/v1/banks/` - List banks
- `POST /api/v1/banks/create` - Create bank
- `DELETE /api/v1/banks/delete?bank_id=X` - Delete bank

### Expenses

- `GET /api/v1/expenses/` - List expenses (with advanced search)
- `GET /api/v1/expenses/graph-data` - Get tag-wise aggregated data
- `POST /api/v1/expenses/create` - Create expense
- `POST /api/v1/expenses/create-bulk` - Bulk create expenses
- `PATCH /api/v1/expenses/add-entry?id=X` - Add entries to expense
- `PATCH /api/v1/expenses/update-entry` - Update entry
- `DELETE /api/v1/expenses/delete-entry?id=X&ee_id=Y` - Delete entry
- `DELETE /api/v1/expenses/delete?id=X` - Delete expense

### Entry Tags

- `GET /api/v1/entry-tags/` - List tags
- `POST /api/v1/entry-tags/create` - Create tag

### User Preferences

- `GET /api/v1/user-preferences/` - Get preferences
- `PATCH /api/v1/user-preferences/update` - Update preferences

## 💡 Usage Examples

### 1. Register a new user

```bash
curl -X POST "http://localhost:8000/api/v1/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "johndoe",
    "password": "securepass123"
  }'
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/v1/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "password": "securepass123"
  }'
```

Response:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "status_code": 201
}
```

### 3. Create a bank (with authentication)

```bash
curl -X POST "http://localhost:8000/api/v1/banks/create" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Chase Checking",
    "initial_balance": 5000.00,
    "current_balance": 5000.00,
    "total_disbursed_till_now": 0.0
  }'
```

### 4. Create an expense

```bash
curl -X POST "http://localhost:8000/api/v1/expenses/create" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "bank_id": "BANK_ID_HERE",
    "expenses": [
      {
        "amount": 50.00,
        "description": "Grocery shopping",
        "selected_tags": [],
        "type": "expense"
      }
    ],
    "created_at": "7/2/2026 00:00"
  }'
```

## 🔍 Advanced Search

The expense endpoint supports complex queries:

```bash
curl -X GET "http://localhost:8000/api/v1/expenses/?data=%7B%22advanced_search%22%3Atrue%2C%22search_by_tags%22%3A%5B%22tag1%22%5D%2C%22search_by_keyword%22%3A%22grocery%22%2C%22operator%22%3A%22and%22%7D" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📊 MongoDB Indexes (Production)

For optimal performance, create these indexes:

```javascript
// In MongoDB shell
use stalk_my_money

// Users
db.users.createIndex({ "email": 1 }, { unique: true })
db.users.createIndex({ "username": 1 }, { unique: true })

// Banks
db.banks.createIndex({ "user_id": 1 })

// Expenses
db.expenses.createIndex({ "user_id": 1, "created_at": -1 })
db.expenses.createIndex({ "bank_id": 1, "user_id": 1 })
db.expenses.createIndex({ "expenses.entry_tags": 1 })

// Tags
db.expense_entry_tags.createIndex({ "user_id": 1, "name": 1 }, { unique: true })

// User Preferences
db.user_preferences.createIndex({ "user_id": 1 }, { unique: true })
```

## 🧪 Testing

```bash
pytest
```

## 🔧 Development

### Code Formatting

```bash
black app/
```

### Running with auto-reload

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🚢 Production Deployment

### Update environment variables

- Set `DEBUG=False`
- Use strong `SECRET_KEY`
- Configure `BACKEND_CORS_ORIGINS`
- Use production MongoDB instance

### Run with Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## 🆚 Differences from Flask Version

| Feature          | Flask (TraceMyMoney) | FastAPI (StalkMyMoney) |
| ---------------- | -------------------- | ---------------------- |
| Framework        | Flask                | FastAPI                |
| Database ORM     | MongoEngine          | Motor (async)          |
| Validation       | Manual               | Pydantic (automatic)   |
| Async            | Sync                 | Async/await            |
| Documentation    | Manual               | Auto-generated         |
| Type Safety      | Minimal              | Full type hints        |
| Password Hashing | Werkzeug             | Argon2                 |
| API Style        | Mixed                | RESTful                |

## 🎯 Key Improvements

1. **Async/Await** - Better performance with async MongoDB operations
2. **Type Safety** - Full type hints throughout
3. **Auto Documentation** - Swagger UI and ReDoc out of the box
4. **Better Validation** - Pydantic models with automatic validation
5. **Modern Python** - Uses Python 3.11+ features
6. **Cleaner Code** - Service layer pattern, dependency injection

## 📝 Environment Variables

| Variable                      | Description     | Default                   |
| ----------------------------- | --------------- | ------------------------- |
| `PROJECT_NAME`                | API name        | Stalk My Money API        |
| `VERSION`                     | API version     | 1.0.0                     |
| `API_V1_STR`                  | API prefix      | /api/v1                   |
| `DEBUG`                       | Debug mode      | False                     |
| `MONGODB_URL`                 | MongoDB URL     | mongodb://localhost:27017 |
| `MONGODB_DB_NAME`             | Database name   | stalk_my_money            |
| `SECRET_KEY`                  | JWT secret      | -                         |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry    | 30                        |
| `BACKEND_CORS_ORIGINS`        | Allowed origins | []                        |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT

## 🙏 Acknowledgments

Converted from the original Flask "TraceMyMoney" application.
