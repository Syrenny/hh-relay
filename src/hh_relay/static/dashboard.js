document.querySelector("#copy-letter")?.addEventListener("click", async () => {
  const text = document.querySelector("#letter-text")?.value;
  if (!text) return;
  await navigator.clipboard.writeText(text);
  const button = document.querySelector("#copy-letter");
  button.textContent = "Скопировано";
  window.setTimeout(() => { button.textContent = "Скопировать"; }, 1600);
});
