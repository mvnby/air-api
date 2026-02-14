document.addEventListener("DOMContentLoaded", function () {
    // Wait a bit to ensure SQLAdmin components are rendered
    setTimeout(() => {
        const nav = document.querySelector(".navbar-nav");
        if (nav && !document.getElementById("rebuild-site-btn")) {
            const li = document.createElement("li");
            li.className = "nav-item ms-lg-3";
            li.innerHTML = `
                <button id="rebuild-site-btn" class="nav-link btn btn-link text-warning d-flex align-items-center gap-1" style="border: 1px solid rgba(255,193,7,0.3); border-radius: 8px; margin-top: 4px; padding: 4px 12px;">
                    <i class="fa fa-bolt"></i>
                    <span>Обновить сайт</span>
                </button>
            `;
            nav.appendChild(li);

            document.getElementById("rebuild-site-btn").addEventListener("click", async function (e) {
                e.preventDefault();
                if (!confirm("Вы уверены, что хотите запустить пересборку сайта? (~2 минуты)")) return;

                const btn = this;
                const originalContent = btn.innerHTML;
                btn.disabled = true;
                btn.style.opacity = "0.6";
                btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> <span>Сборка...</span>';

                try {
                    const response = await fetch("/api/system/rebuild-web", {
                        method: "POST",
                        headers: {
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        }
                    });
                    const result = await response.json();
                    if (response.ok) {
                        alert(result.message || "Сборка успешно запущена!");
                    } else {
                        alert("Ошибка: " + (result.detail || "Не удалось запустить сборку"));
                    }
                } catch (err) {
                    alert("Ошибка сети: " + err.message);
                } finally {
                    btn.disabled = false;
                    btn.style.opacity = "1";
                    btn.innerHTML = originalContent;
                }
            });
        }
    }, 500);
});
