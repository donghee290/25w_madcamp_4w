const mongoose = require('mongoose');
require('dotenv').config();
const UserAuth = require('./models/UserAuth');
const UserInfo = require('./models/UserInfo');

const MONGO_URI = process.env.MONGO_URI;

mongoose.connect(MONGO_URI)
    .then(async () => {
        console.log('✅ MongoDB Connected for Reset');

        try {
            // 모든 사용자 데이터 삭제
            await UserAuth.deleteMany({});
            await UserInfo.deleteMany({});
            console.log('🗑️ All users (Auth & Info) deleted successfully.');

            // 혹시 다른 컬렉션이 있다면 여기서 추가로 삭제 가능
            // await mongoose.connection.db.dropCollection('projects'); 

        } catch (error) {
            console.error('❌ Error clearing database:', error);
        } finally {
            mongoose.disconnect();
            console.log('👋 Disconnected');
        }
    })
    .catch(err => console.error('❌ Connection Error:', err));
