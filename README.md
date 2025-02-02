# Onchain Angels Backend

## 🚀 Environment Setup

### Prerequisites
- Python 3.10+
- Pipenv
- PostgreSQL
- [ngrok](https://dashboard.ngrok.com/signup)

### Installation
1. Clone the repository
```bash
git clone [repository-url]
cd onchain-angels-backend
```

2. Install dependencies
```bash
pipenv install
pipenv shell
```

3. Set up environment variables
```bash
cp .env.example .env # Edit the .env file with your settings
```

## 🔧 Development

### Running the local server
```bash
python manage.py runserver
```

### Setting up ngrok
1. Start your local forwarding tunnel:
```bash
ngrok http --url=poodle-just-instantly.ngrok-free.app 8000 # Replace with your ngrok subdomain
```

2. Web Inspection Interface:
```
http://localhost:4040/inspect/http
```

## 📚 API Documentation
- [Swagger-ui](https://api.onchain-angels.com/api/v1/schema/swagger-ui/)
- [Redoc](https://api.onchain-angels.com/api/v1/schema/redoc/)
