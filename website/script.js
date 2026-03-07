const STORAGE_KEY = 'truth-site-questions-v1';

const form = document.getElementById('question-form');
const nameInput = document.getElementById('name');
const questionInput = document.getElementById('question');
const privateInput = document.getElementById('private');
const formMessage = document.getElementById('form-message');
const list = document.getElementById('question-list');
const clearBtn = document.getElementById('clear-btn');

function getQuestions() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveQuestions(questions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(questions));
}

function renderQuestions() {
  const questions = getQuestions();
  list.innerHTML = '';

  if (questions.length === 0) {
    const empty = document.createElement('li');
    empty.textContent = 'No public questions yet.';
    empty.className = 'meta';
    list.appendChild(empty);
    return;
  }

  questions.forEach((entry) => {
    const li = document.createElement('li');
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = `${entry.name || 'Anonymous'} • ${new Date(entry.createdAt).toLocaleString()}`;
    const body = document.createElement('div');
    body.textContent = entry.question;
    li.append(meta, body);
    list.appendChild(li);
  });
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  formMessage.classList.remove('error');

  const question = questionInput.value.trim();
  if (!question) {
    formMessage.textContent = 'Please write a question before submitting.';
    formMessage.classList.add('error');
    return;
  }

  const isPrivate = privateInput.checked;
  if (!isPrivate) {
    const questions = getQuestions();
    questions.unshift({
      name: nameInput.value.trim(),
      question,
      createdAt: Date.now(),
    });
    saveQuestions(questions.slice(0, 25));
    renderQuestions();
  }

  form.reset();
  formMessage.textContent = isPrivate
    ? 'Question saved privately (not shown on wall).'
    : 'Question submitted to the public wall.';
});

clearBtn.addEventListener('click', () => {
  localStorage.removeItem(STORAGE_KEY);
  renderQuestions();
  formMessage.classList.remove('error');
  formMessage.textContent = 'Local questions cleared.';
});

renderQuestions();
