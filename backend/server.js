const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { createProxyMiddleware } = require('http-proxy-middleware');
require('dotenv').config({ path: __dirname + '/.env' });

const app = express();
const PORT = process.env.PORT || 5000;
const MONGO_URI = process.env.MONGO_URI || 'mongodb://127.0.0.1:27017/soundroutine';
const JWT_SECRET = process.env.JWT_SECRET || 'soundroutine_secret_key';
const MODEL_BASE_URL = process.env.MODEL_BASE_URL || 'http://127.0.0.1:8001';

// Middleware
app.use(cors());

// Proxy model API (Flask) through Node
app.use('/api', createProxyMiddleware({
    target: MODEL_BASE_URL,
    changeOrigin: true,
    proxyTimeout: 300000,
    timeout: 300000
}));

app.use(express.json());

// MongoDB Connection
mongoose.connect(MONGO_URI)
    .then(() => console.log('✅ MongoDB Connected'))
    .catch(err => console.error('❌ MongoDB Connection Error:', err));

// --- User Models ---
const UserAuth = require('./models/UserAuth');
const UserInfo = require('./models/UserInfo');

// --- Routes ---

// Register
app.post('/auth/register', async (req, res) => {
    try {
        console.log('📝 Register Request Body:', req.body);
        const { id, password, name, job } = req.body;

        if (!id || !password || !name || !job) {
            console.log('❌ Missing fields');
            return res.status(400).json({ message: 'All fields are required' });
        }

        // 1. Check if user already exists in Auth
        const existingUser = await UserAuth.findOne({ id });
        if (existingUser) {
            console.log('⚠️ User already exists:', id);
            return res.status(400).json({ message: 'User ID already exists' });
        }

        // 2. Hash password
        const hashedPassword = await bcrypt.hash(password, 10);

        // 3. Create UserAuth (Login credentials)
        const newUserAuth = new UserAuth({
            id,
            password: hashedPassword
        });
        await newUserAuth.save();

        // 4. Create UserInfo (Profile details)
        const newUserInfo = new UserInfo({
            id,
            name,
            job
        });
        await newUserInfo.save();

        res.status(201).json({ message: 'User registered successfully' });
    } catch (err) {
        console.error(err);
        // 롤백 로직이 있으면 좋지만 간단하게 구현 (auth 저장 후 info 실패 시 auth는 남을 수 있음 -> 추후 트랜잭션 고려 가능)
        res.status(500).json({ message: 'Server error during registration' });
    }
});

// Login
app.post('/auth/login', async (req, res) => {
    try {
        const { id, password } = req.body;

        // 1. Find Auth Info
        const userAuth = await UserAuth.findOne({ id });
        if (!userAuth) {
            return res.status(400).json({ message: 'Invalid credentials' });
        }

        // 2. Check Password
        const isMatch = await bcrypt.compare(password, userAuth.password);
        if (!isMatch) {
            return res.status(400).json({ message: 'Invalid credentials' });
        }

        // 3. Find User Info (Name, Job)
        const userInfo = await UserInfo.findOne({ id });

        // 4. Create Token
        const token = jwt.sign({ id: userAuth.id }, JWT_SECRET, { expiresIn: '1h' });

        res.json({
            accessToken: token,
            user: {
                id: userAuth.id,
                name: userInfo ? userInfo.name : 'Unknown',
                job: userInfo ? userInfo.job : 'Unknown'
            }
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ message: 'Server error during login' });
    }
});

// Start Server
app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
