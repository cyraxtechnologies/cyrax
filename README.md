# 🤖 Cyrax - AI Financial Assistant on WhatsApp

Your AI-powered financial companion for South Africa, operating entirely on WhatsApp.

## 🚀 Features

- **💸 Send Money** - Transfer money via phone numbers
- **📱 Buy Airtime** - Purchase airtime for any network (MTN, Vodacom, Cell C, Telkom)
- **⚡ Pay Electricity** - Buy prepaid electricity tokens
- **💰 Check Balance** - Real-time account balance
- **📊 Transaction History** - View recent transactions
- **🎤 Voice Notes** - Speak naturally, AI understands
- **📸 Image Recognition** - Take photos of account numbers
- **🔐 Secure** - PIN-protected transactions with FICA compliance

---

## 📋 Prerequisites

- **Python 3.11+**
- **PostgreSQL 15+**
- **Redis 7+**
- **Docker & Docker Compose** (optional but recommended)
- **WhatsApp Business API Account**
- **OpenAI API Key**
- **PayStack Account**

---

## 🛠️ Installation

### Quick Start
```bash
# Clone or create project
mkdir cyrax && cd cyrax

# Copy all files from artifacts into this directory

# Make setup script executable
chmod +x quickstart.sh

# Run setup
./quickstart.sh
```

### Manual Installation
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python -c "from app.database import init_db; init_db()"

# Run application
uvicorn app.main:app --reload
```

### Docker Installation
```bash
# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f app
```

---

## ⚙️ Configuration

Edit `.env` file with your credentials:
```bash
# WhatsApp Business API
WHATSAPP_PHONE_NUMBER_ID=your_phone_id
WHATSAPP_ACCESS_TOKEN=your_token

# OpenAI
OPENAI_API_KEY=sk-your-key

# PayStack
PAYSTACK_SECRET_KEY=sk_test_your_key

# Database
DATABASE_URL=postgresql://cyrax_user:password@localhost:5432/cyrax_db
```

---

## 🚀 Usage

1. **Start Cyrax**:
```bash
uvicorn app.main:app --reload
```

2. **Expose with ngrok** (for testing):
```bash
ngrok http 8000
```

3. **Configure WhatsApp webhook**: Use your ngrok URL

4. **Send a message**: "Hi Cyrax"

---

## 📱 Example Conversations
```
You: Hi
Cyrax: 👋 Hi! Welcome to Cyrax! I'm your AI financial assistant...

You: Send R100 to 0821234567
Cyrax: Please confirm: Send R100.00 to 0821234567...
You: YES
Cyrax: 🔐 Please enter your PIN:
You: 1234
Cyrax: ✅ Successfully sent R100.00...

You: Check balance
Cyrax: 💰 Available: R500.00...

You: Buy R50 MTN airtime
Cyrax: Please confirm: Buy R50.00 MTN airtime...
```

---

## 🔒 Security

- PIN-protected transactions
- FICA compliance
- End-to-end encryption (WhatsApp)
- Fraud detection
- Rate limiting

---

## 📊 Monitoring
```bash
# Health check
curl http://localhost:8000/health

# Platform stats
curl http://localhost:8000/admin/stats
```

---

## 🐛 Troubleshooting

**Webhook not working?**
- Check ngrok is running
- Verify WhatsApp webhook subscription
- Check logs: `docker-compose logs -f app`

**Database errors?**
- Verify PostgreSQL is running
- Check DATABASE_URL in .env

---

## 💰 Cost Estimate (5,000 users/month)

- AWS EC2: R400
- WhatsApp API: R3,000
- OpenAI: R1,500
- PayStack: Transaction-based
- **Total: ~R5,000/month**

---

## 📄 License

MIT License

---

## 🙏 Built With

- FastAPI
- OpenAI GPT-4
- WhatsApp Business API
- PayStack
- PostgreSQL
- Redis

---

**Ready to launch Cyrax! 🚀**

For support: support@cyrax.co.za
