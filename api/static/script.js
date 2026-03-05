// api/static/script.js

// Инициализация Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand();
tg.setHeaderColor('#0B0E1A');

// Получаем данные пользователя из initDataUnsafe
let userId = null;
let initData = '';
try {
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        userId = tg.initDataUnsafe.user.id;
        initData = tg.initData; // строка initData для аутентификации
        console.log('User ID:', userId);
    } else {
        console.warn('No user data, using test mode');
        userId = 123456789;
        initData = ''; // в тестовом режиме аутентификация не пройдёт
    }
} catch (e) {
    console.error('Failed to get user ID', e);
    userId = 123456789;
    initData = '';
}

// Глобальные переменные
let balance = 0;
let timeLeft = 60;
let betsCount = 0;
let timerInterval = null;
let lastWinsInterval = null;
let bannerShown = false;

// WebSocket переменные
let socket = null;
let currentRoom = 'general';
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

// Элементы DOM
const balanceEl = document.getElementById('balance');
const timerEl = document.getElementById('timer');
const timerProgress = document.getElementById('timerProgress');
const betsCountEl = document.getElementById('betsCount');
const winsList = document.getElementById('winsList');
const banner = document.getElementById('banner');
const profileBtn = document.getElementById('profileBtn');
const betButtons = document.querySelectorAll('.bet-btn');
const tabBtns = document.querySelectorAll('.tab-btn');
const gameTab = document.getElementById('game-tab');
const chatTab = document.getElementById('chat-tab');
const chatMessagesEl = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendChatBtn = document.getElementById('sendChatBtn');

// Функция для обновления баланса с сервера
async function fetchBalance() {
    try {
        const response = await fetch(`/api/user/balance`, {
            headers: {
                'X-Telegram-User-Id': userId
            }
        });
        if (!response.ok) throw new Error('Failed to fetch balance');
        const data = await response.json();
        balance = data.balance;
        balanceEl.textContent = balance;
        
        if (balance < 500 && !bannerShown) {
            banner.style.display = 'block';
            bannerShown = true;
        } else if (balance >= 500) {
            banner.style.display = 'none';
            bannerShown = false;
        }
    } catch (e) {
        console.error('Balance fetch error:', e);
    }
}

// Функция для получения информации о текущем раунде
async function fetchRoundInfo() {
    try {
        const response = await fetch('/api/game/round_info');
        if (!response.ok) throw new Error('Failed to fetch round info');
        const data = await response.json();
        timeLeft = data.time_left;
        betsCount = data.bets_count;
        betsCountEl.textContent = betsCount;
    } catch (e) {
        console.error('Round info error:', e);
    }
}

// Функция для обновления таймера
function updateTimer() {
    if (timeLeft <= 0) {
        fetchRoundInfo();
    } else {
        timeLeft--;
    }
    
    const seconds = Math.floor(timeLeft);
    timerEl.textContent = seconds < 10 ? '0' + seconds : seconds;
    
    const total = 60;
    const progress = (timeLeft / total) * 339.292;
    timerProgress.style.strokeDashoffset = progress;
}

// Функция для размещения ставки
async function placeBet(amount) {
    const btn = Array.from(betButtons).find(b => b.dataset.amount == amount);
    if (btn) btn.disabled = true;
    
    try {
        const response = await fetch('/api/game/place_bet', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-User-Id': userId
            },
            body: JSON.stringify({ amount })
        });
        
        const data = await response.json();
        if (!response.ok) {
            tg.showAlert(data.detail || 'Ошибка при размещении ставки');
            return;
        }
        
        balance = data.new_balance;
        balanceEl.textContent = balance;
        tg.HapticFeedback.impactOccurred('medium');
        
        if (data.message) {
            tg.showPopup({
                title: 'Ставка принята',
                message: data.message,
                buttons: [{ type: 'ok' }]
            });
        }
    } catch (e) {
        console.error('Place bet error:', e);
        tg.showAlert('Ошибка соединения');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Функция для загрузки последних выигрышей
async function fetchLastWins() {
    try {
        const response = await fetch('/api/game/last_wins?limit=10');
        if (!response.ok) throw new Error('Failed to fetch last wins');
        const data = await response.json();
        
        winsList.innerHTML = '';
        if (data.wins.length === 0) {
            winsList.innerHTML = '<li class="win-item loading">Пока нет выигрышей</li>';
        } else {
            data.wins.forEach(win => {
                const li = document.createElement('li');
                li.className = 'win-item';
                li.innerHTML = `<span>${win.username}</span><span class="win-amount">+${win.amount} ⭐</span>`;
                winsList.appendChild(li);
            });
        }
    } catch (e) {
        console.error('Last wins error:', e);
        winsList.innerHTML = '<li class="win-item loading">Ошибка загрузки</li>';
    }
}

// ---------- WebSocket чат ----------
function connectWebSocket() {
    if (socket && socket.readyState === WebSocket.OPEN) return;
    
    // Если нет initData (тестовый режим), не подключаемся
    if (!initData) {
        console.warn('No initData, cannot connect to chat');
        return;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/chat/ws/${currentRoom}?init_data=${encodeURIComponent(initData)}`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'history') {
            chatMessagesEl.innerHTML = '';
            data.data.forEach(msg => appendMessage(msg));
        } else if (data.type === 'message') {
            appendMessage(data.data);
        } else if (data.type === 'system') {
            appendSystemMessage(data.data);
        }
    };

    socket.onclose = () => {
        console.log('WebSocket disconnected');
        // Пытаемся переподключаться, если вкладка чата активна
        if (chatTab.classList.contains('active') && reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, 3000 * reconnectAttempts);
        }
    };

    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function appendMessage(msg) {
    const div = document.createElement('div');
    div.className = 'chat-message';
    const time = new Date(msg.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    div.innerHTML = `<span class="chat-user">${msg.username}</span> <span class="chat-time">${time}</span><br>${msg.message}`;
    chatMessagesEl.appendChild(div);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'chat-system';
    div.textContent = text;
    chatMessagesEl.appendChild(div);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

// ---------- Обработчики ----------
betButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const amount = parseInt(btn.dataset.amount, 10);
        placeBet(amount);
    });
});

profileBtn.addEventListener('click', () => {
    tg.openTelegramLink(`https://t.me/${tg.initDataUnsafe?.user?.username || 'starsobot_bot'}?start=profile`);
});

// Переключение вкладок
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        
        if (tab === 'game') {
            gameTab.classList.add('active');
            chatTab.classList.remove('active');
            if (socket) socket.close();
        } else {
            gameTab.classList.remove('active');
            chatTab.classList.add('active');
            connectWebSocket();
        }
    });
});

// Отправка сообщения
sendChatBtn.addEventListener('click', () => {
    const text = chatInput.value.trim();
    if (text && socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ message: text }));
        chatInput.value = '';
    }
});

chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatBtn.click();
});

// Инициализация при загрузке
async function init() {
    await fetchBalance();
    await fetchRoundInfo();
    await fetchLastWins();
    
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(updateTimer, 1000);
    
    setInterval(fetchBalance, 10000);
    setInterval(fetchRoundInfo, 5000);
    setInterval(fetchLastWins, 15000);
}

init();
tg.ready();
