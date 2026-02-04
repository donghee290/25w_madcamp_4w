const mongoose = require('mongoose');

// 인증 정보 (로그인용)
const userAuthSchema = new mongoose.Schema({
    id: {
        type: String,
        required: true,
        unique: true
    },
    password: {
        type: String,
        required: true
    },
    createdAt: {
        type: Date,
        default: Date.now
    }
});

const UserAuth = mongoose.model('UserAuth', userAuthSchema, 'auths');
module.exports = UserAuth;
