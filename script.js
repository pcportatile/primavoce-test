const today = document.querySelector('#today');
const menuBtn = document.querySelector('#menuBtn');
const mainNav = document.querySelector('#mainNav');
const navLinks = document.querySelectorAll('.nav-link');
const items = document.querySelectorAll('.article-item');

const formattedDate = new Intl.DateTimeFormat('it-IT', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
}).format(new Date());
today.textContent = formattedDate;

menuBtn.addEventListener('click', () => {
  const isOpen = mainNav.classList.toggle('open');
  menuBtn.setAttribute('aria-expanded', String(isOpen));
});

navLinks.forEach(link => link.addEventListener('click', () => {
  navLinks.forEach(item => item.classList.remove('active'));
  link.classList.add('active');
  const category = link.dataset.category;
  items.forEach(item => {
    const categories = item.dataset.category.split(' ');
    item.classList.toggle('hidden', category !== 'tutte' && !categories.includes(category));
  });
  if (window.innerWidth <= 800) {
    mainNav.classList.remove('open');
    menuBtn.setAttribute('aria-expanded', 'false');
  }
}));

document.querySelector('#newsletterForm').addEventListener('submit', event => {
  event.preventDefault();
  const email = document.querySelector('#email');
  document.querySelector('#formMessage').textContent = `Grazie! Demo iscrizione registrata per ${email.value}.`;
  event.target.reset();
});
