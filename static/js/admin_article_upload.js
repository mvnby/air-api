document.addEventListener("DOMContentLoaded", function () {
    // Check if we are on Article page
    const isArticlePage = window.location.pathname.includes("/admin/article/create") ||
        window.location.pathname.includes("/admin/article/edit");

    if (!isArticlePage) return;

    const toolbar = document.querySelector(".editor-toolbar");
    if (!toolbar) {
        console.log("SimpleMDE toolbar not found");
        return;
    }

    // Create separator
    const separator = document.createElement("i");
    separator.className = "separator";
    separator.innerHTML = "|";
    toolbar.appendChild(separator);

    // Create Button
    const btn = document.createElement("a");
    btn.className = "fa fa-images";
    btn.title = "Загрузить фото (Мульти)";
    btn.style.cursor = "pointer";
    toolbar.appendChild(btn);

    // Create Hidden Input
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = "image/*";
    input.style.display = "none";
    document.body.appendChild(input);

    // Handle Click
    btn.addEventListener("click", function () {
        input.click();
    });

    // Handle Change
    input.addEventListener("change", async function () {
        if (this.files.length === 0) return;

        // Visual feedback
        const oldClass = btn.className;
        btn.className = "fa fa-spinner fa-spin";

        try {
            const formData = new FormData();
            for (let i = 0; i < this.files.length; i++) {
                formData.append("files", this.files[i]);
            }

            // Get slug if available
            const slugInput = document.querySelector('input[name="slug"]');
            if (slugInput && slugInput.value) {
                formData.append("slug", slugInput.value);
            }

            const response = await fetch("/admin/api/upload_images", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                throw new Error("Upload failed");
            }

            const data = await response.json();

            // Generate Markdown
            let markdown = "";
            data.urls.forEach(url => {
                markdown += `\n![](${url})\n`;
            });

            // Insert into Editor
            const cmElement = document.querySelector(".CodeMirror");
            if (cmElement && cmElement.CodeMirror) {
                const doc = cmElement.CodeMirror.getDoc();
                const cursor = doc.getCursor();
                doc.replaceRange(markdown, cursor);
            } else {
                // Fallback to textarea
                const textarea = document.querySelector('textarea[name="content"]');
                if (textarea) {
                    textarea.value += markdown;
                }
            }

        } catch (error) {
            console.error(error);
            alert("Ошибка загрузки: " + error.message);
        } finally {
            btn.className = oldClass;
            input.value = ""; // Reset
        }
    });

    console.log("Multi-Upload Plugin initialized");
});
