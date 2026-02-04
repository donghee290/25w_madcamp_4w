const mongoose = require('mongoose');

// 사용자 상세 정보 (프로필용)
const userInfoSchema = new mongoose.Schema({
    id: {
        type: String,
        required: true,
        unique: true,
        ref: 'UserAuth' // UserAuth의 id를 참조 (논리적 참조)
    },
    name: {
        type: String,
        required: true
    },
    job: {
        type: String,
        required: true
    }
});

const UserInfo = mongoose.model('UserInfo', userInfoSchema, 'users');
module.exports = UserInfo;
