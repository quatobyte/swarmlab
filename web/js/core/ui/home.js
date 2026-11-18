// Язык стартовых экранов. Редактор, обучение и API сохраняют русские названия команд.
const EN = {
  login: 'Sign in', register: 'Register', email: 'Email address', password: 'Password', repeat: 'Repeat password',
  createAccount: 'Create account', guest: 'Continue without signing in →', contest: 'I have a competition code',
  projects: 'Projects', myProjects: 'My projects', learning: 'Learning', reference: 'Reference',
  profile: 'My profile', logout: 'Sign out', welcome: 'Your next idea starts here',
  intro: 'Create programs and watch the swarm in action.', import: 'Import .swarm',
  newProject: 'New project', newIdea: 'Start with your own idea', learnTry: 'Learn and experiment',
  learningKicker: '01 / LEARNING', learningTitle: 'From your first agent to a swarm',
  learningDescription: '8 missions with in-game hints', startLearning: 'Start learning →',
  examplesKicker: '02 / EXAMPLES', examplesTitle: 'See how it works',
  examplesDescription: 'Open a program and make it your own', openExamples: 'Open examples →',
  referenceKicker: '03 / REFERENCE', referenceTitle: 'Find the right block',
  referenceDescription: 'Commands, sensors and world rules', openReference: 'Open reference →',
  matchTools: 'Matches and editor', replays: 'My replays', footer: 'Made to explore swarm systems',
  signInNote: 'Forgot your password? Contact the administrator.',
  registerNote: 'Email is your username; no messages are sent. Use at least 8 characters. The administrator can help reset your password.',
  passwordPlaceholder: 'Enter your password', newPasswordPlaceholder: 'Choose a password',
  later: 'This mode is coming later.', mismatch: 'Passwords do not match',
  newProjectTitle: 'New project', projectName: 'File name (Latin letters, numbers and _)', create: 'Create', cancel: 'Cancel',
};
const RU = {
  createAccount: 'Создать аккаунт', login: 'Войти', signInNote: 'Забыли пароль? Обратитесь к администратору.',
  registerNote: 'Почта — ваш логин, писем не будет. Пароль — не меньше 8 символов; забудете — поможет админ.',
  passwordPlaceholder: 'Введите пароль', newPasswordPlaceholder: 'Придумайте пароль',
  later: 'Режим появится позже.', mismatch: 'Пароли не совпадают',
  newProjectTitle: 'Новый проект', projectName: 'Имя файла (латиница, цифры и _)', create: 'Создать', cancel: 'Отмена',
};
let language = 'ru';
try { if (localStorage.getItem('swarmlab.language') === 'en') language = 'en'; } catch { /* браузер без хранилища */ }

export function text(key) { return (language === 'en' ? EN : RU)[key] || key; }

export function initHome({ newProject, examples, reference, learning }) {
  const nodes = [...document.querySelectorAll('[data-i18n]')];
  const originals = new Map(nodes.map(n => [n, n.textContent]));
  const apply = () => {
    document.documentElement.lang = language;
    for (const n of nodes) n.textContent = language === 'en' ? EN[n.dataset.i18n] || originals.get(n) : originals.get(n);
    for (const n of document.querySelectorAll('[data-language]')) n.setAttribute('aria-pressed', String(n.dataset.language === language));
    document.querySelector('.auth-subtitle').hidden = language === 'en';
    document.querySelector('.auth-subtitle-en').hidden = language !== 'en';
    document.dispatchEvent(new Event('swarmlab:language'));
  };
  for (const n of document.querySelectorAll('[data-language]')) n.onclick = () => {
    language = n.dataset.language;
    try { localStorage.setItem('swarmlab.language', language); } catch { /* браузер без хранилища */ }
    apply();
  };
  document.getElementById('home-new-project').onclick = newProject;
  document.getElementById('home-examples').onclick = examples;
  document.getElementById('home-help').onclick = reference;
  document.getElementById('home-reference').onclick = reference;
  document.getElementById('home-learning').onclick = learning;
  document.getElementById('help').onclick = e => {
    if (e.target.id === 'help' || e.target.classList.contains('close')) document.getElementById('help').hidden = true;
  };
  document.querySelector('[data-home-scroll]').onclick = e => {
    e.preventDefault();
    document.getElementById('home-projects').scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  apply();
}

/** Карточки используют те же обработчики открытия, экспорта и удаления, что старый список. */
export function projectCard(row, open) {
  row.className = 'project-card';
  const preview = document.createElement('img');
  preview.className = 'project-preview';
  preview.src = 'assets/brand/meadow.svg';
  preview.alt = '';
  preview.width = 300;
  preview.height = 148;
  // Открытие доступно клавиатурой через явную кнопку под обложкой.
  preview.onclick = open;
  const actions = document.createElement('div');
  actions.className = 'project-actions';
  actions.append(...row.querySelectorAll('button'));
  row.prepend(preview);
  row.append(actions);
  return row;
}
