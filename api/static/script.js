// api/static/script.js

// Инициализация Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand(); // Растягиваем на весь экран
tg.setHeaderColor('#0B0E1A'); // Тёмный цвет под фон

// Получаем данные пользователя из initDataUnsafe
let userId = null;
try {
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        userId = tg.initDataUnsafe.user.id;
        console.log('User ID:', userId);
    } else {
        console.warn('No user data, using test mode');
        userId = 123456789; // для теста
    }
} catch (e) {
    console.error('Failed to get user ID', e);
    userId = 123456789;
}

// Глобальные переменные
let balance = 0;
let timeLeft = 60;
let betsCount = 0;
let timerInterval = null;
let lastWinsInterval = null;
let bannerShown = false;

// Элементы DOM
const balanceEl = document.getElementById('balance');
const timerEl = document.getElementById('timer');
const timerProgress = document.getElementById('timerProgress');
const betsCountEl = document.getElementById('betsCount');
const winsList = document.getElementById('winsList');
const banner = document.getElementById('banner');
const profileBtn = document.getElementById('profileBtn');
const betButtons = document.querySelectorAll('.bet-btn');

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
        
        // Показываем баннер, если баланс ниже порога (например, < 500) и ещё не показывали
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

// Функция для обновления таймера (вызывается каждую секунду)
function updateTimer() {
    if (timeLeft <= 0) {
        // Время вышло, обновляем информацию
        fetchRoundInfo().then(() => {
            // после обновления таймер начнёт новую минуту
        });
    } else {
        timeLeft--;
    }
    
    const seconds = Math.floor(timeLeft);
    timerEl.textContent = seconds < 10 ? '0' + seconds : seconds;
    
    // Обновляем прогресс (окружность)
    const total = 60;
    const progress = (timeLeft / total) * 339.292; // длина окружности 2*pi*54 ≈ 339.292
    timerProgress.style.strokeDashoffset = progress;
}

// Функция для размещения ставки
async function placeBet(amount) {
    // Блокируем кнопку на время запроса
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
            // Показываем ошибку
            tg.showAlert(data.detail || 'Ошибка при размещении ставки');
            return;
        }
        
        // Обновляем баланс
        balance = data.new_balance;
        balanceEl.textContent = balance;
        
        // Вибрация (если поддерживается)
        tg.HapticFeedback.impactOccurred('medium');
        
        // Если есть сообщение (например, про баннер), покажем уведомление
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
                const date = new Date(win.time);
                const timeStr = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                li.innerHTML = `<span>${win.username}</span><span class="win-amount">+${win.amount} ⭐</span>`;
                winsList.appendChild(li);
            });
        }
    } catch (e) {
        console.error('Last wins error:', e);
        winsList.innerHTML = '<li class="win-item loading">Ошибка загрузки</li>';
    }
}

// Обработчики кнопок ставок
betButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        const amount = parseInt(btn.dataset.amount, 10);
        placeBet(amount);
    });
});

// Обработчик кнопки профиля
profileBtn.addEventListener('click', () => {
    // Открываем профиль в боте (можно через команду /profile или ссылку)
    tg.openTelegramLink(`https://t.me/${tg.initDataUnsafe?.user?.username || 'starsobot_bot'}?start=profile`);
    // Либо можно открыть отдельную страницу профиля внутри Mini App, но для простоты отправим в бота
});

// Инициализация при загрузке
async function init() {
    await fetchBalance();
    await fetchRoundInfo();
    await fetchLastWins();
    
    // Запускаем таймер
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(updateTimer, 1000);
    
    // Обновляем баланс и информацию о раунде каждые 10 секунд
    setInterval(fetchBalance, 10000);
    setInterval(fetchRoundInfo, 5000);
    setInterval(fetchLastWins, 15000);
}

// Стартуем
init();

// Сообщаем Telegram, что приложение готово
tg.ready();
