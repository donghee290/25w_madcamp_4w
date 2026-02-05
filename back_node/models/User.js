const mongoose = require('mongoose');

// User Schema Definition
const userSchema = new mongoose.Schema({
    id: {
        type: String,
        required: true,
        unique: true
    },
    password: {
        type: String,
        required: true
    },
    name: {
        type: String,
        required: true
    },
    job: {
        type: String,
        required: true
    },
    createdAt: {
        type: Date,
        default: Date.now
    }
});

// Create and export the model
// MongoDB will automatically create a collection named 'users' (plural of 'User')
const User = mongoose.model('User', userSchema);
module.exports = User;
