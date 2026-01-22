document.addEventListener("DOMContentLoaded", function () {
    const isArticlePage = window.location.pathname.includes("/admin/article/create") ||
        window.location.pathname.includes("/admin/article/edit");

    if (!isArticlePage) return;

    // --- Configuration ---
    const CONFIG = {
        apiUpload: "/admin/api/upload_images",
        apiList: "/admin/api/article_images", // + /{slug}
        placeholderId: "article-image-gallery-placeholder"
    };

    // --- State ---
    const state = {
        slug: null,
        galleryContainer: null
    };

    // --- Initialization ---
    function init() {
        // 1. Find Slug
        const slugInput = document.querySelector('input[name="slug"]');
        if (slugInput) {
            state.slug = slugInput.value;
        }

        // 2. Setup Container
        setupGalleryContainer();

        // 3. Load existing images if slug exists
        if (state.slug) {
            loadImages(state.slug);
        } else {
            // If no slug (and we are in edit mode? unlikely with new flow), 
            // or just created, show empty state.
            // In 'create' mode (title only), this script might run but no slug yet.
            renderEmptyState();
        }
    }

    function setupGalleryContainer() {
        let container = document.getElementById(CONFIG.placeholderId);

        // Fallback: if placeholder missing, try to inject after toolbar (legacy support)
        if (!container) {
            const toolbar = document.querySelector(".editor-toolbar");
            if (toolbar) {
                container = document.createElement("div");
                container.id = "article-image-gallery-legacy";
                toolbar.parentNode.insertBefore(container, toolbar.nextSibling);

                // Add upload button to toolbar if we are in legacy mode
                setupToolbarButton(toolbar);
            } else {
                console.warn("Gallery: Placeholders not found.");
                return;
            }
        }

        state.galleryContainer = container;

        // Apply Styles
        Object.assign(container.style, {
            backgroundColor: "#f9fafb",
            border: "2px dashed #d1d5db",
            borderRadius: "0 0 8px 8px", // Matches card bottom usually
            padding: "15px",
            display: "flex",
            flexWrap: "wrap",
            gap: "12px",
            minHeight: "120px",
            transition: "all 0.3s",
            alignItems: "center",
            justifyContent: "flex-start", // Default to start
            marginTop: "0"
        });

        // Drag & Drop Events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            container.addEventListener(eventName, preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            container.addEventListener(eventName, () => {
                container.style.backgroundColor = "#e5e7eb";
                container.style.borderColor = "#3b82f6";
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            container.addEventListener(eventName, () => {
                container.style.backgroundColor = "#f9fafb";
                container.style.borderColor = "#d1d5db";
            }, false);
        });

        container.addEventListener('drop', handleDrop, false);
    }

    function setupToolbarButton(toolbar) {
        // Only needed if we want a button trigger. 
        // We can also just add a "Click here to upload" in the gallery itself.
        // Let's rely on the gallery placeholder text for click-to-upload.
    }

    // --- Core Logic ---

    async function loadImages(slug) {
        try {
            const response = await fetch(`${CONFIG.apiList}/${slug}`);
            if (!response.ok) throw new Error("Failed to load images");

            const data = await response.json();
            if (data.urls && data.urls.length > 0) {
                renderImages(data.urls);
            } else {
                renderEmptyState();
            }
        } catch (e) {
            console.error("Gallery Load Error:", e);
            renderEmptyState();
        }
    }

    function renderEmptyState() {
        if (!state.galleryContainer) return;

        state.galleryContainer.innerHTML = "";
        state.galleryContainer.style.justifyContent = "center";

        const placeholder = document.createElement("div");
        placeholder.innerHTML = '<i class="fa fa-cloud-upload"></i> Перетащите фото сюда или нажмите для выбора';
        placeholder.style.color = "#9ca3af";
        placeholder.style.fontSize = "14px";
        placeholder.style.cursor = "pointer";
        placeholder.style.pointerEvents = "auto";

        // Make the empty state clickable for upload
        placeholder.addEventListener("click", () => fileInput.click());

        state.galleryContainer.appendChild(placeholder);
    }

    function renderImages(urls) {
        if (!state.galleryContainer) return;

        // Clear if it was empty state
        // Check if we have the placeholder text
        const hasPlaceholder = state.galleryContainer.querySelector(".fa-cloud-upload");
        if (hasPlaceholder) {
            state.galleryContainer.innerHTML = "";
            state.galleryContainer.style.justifyContent = "flex-start";
        }

        // Add "Add New" button card
        if (!state.galleryContainer.querySelector(".add-new-card")) {
            createAddButton();
        }

        urls.forEach(url => {
            // Check duplicates
            if (isImageInGallery(url)) return;
            addImageToGallery(url);
        });
    }

    function createAddButton() {
        const wrapper = document.createElement("div");
        wrapper.className = "add-new-card";
        wrapper.style.width = "100px";
        wrapper.style.height = "100px";
        wrapper.style.border = "2px dashed #d1d5db";
        wrapper.style.borderRadius = "6px";
        wrapper.style.display = "flex";
        wrapper.style.alignItems = "center";
        wrapper.style.justifyContent = "center";
        wrapper.style.cursor = "pointer";
        wrapper.style.color = "#9ca3af";
        wrapper.innerHTML = '<i class="fa fa-plus"></i>';

        wrapper.addEventListener("click", () => fileInput.click());
        // Insert as first child
        state.galleryContainer.insertBefore(wrapper, state.galleryContainer.firstChild);
    }

    function isImageInGallery(url) {
        // Simple check based on src
        const existing = state.galleryContainer.querySelectorAll("img");
        for (let img of existing) {
            if (img.src.includes(url)) return true;
        }
        return false;
    }

    function addImageToGallery(url) {
        const wrapper = document.createElement("div");
        wrapper.style.position = "relative";
        wrapper.style.width = "100px";
        wrapper.style.height = "100px";
        wrapper.style.border = "1px solid #e5e7eb";
        wrapper.style.borderRadius = "6px";
        wrapper.style.overflow = "hidden";
        wrapper.style.cursor = "pointer";
        wrapper.style.backgroundColor = "#fff";
        wrapper.title = "Кликните для вставки markdown";

        const img = document.createElement("img");
        img.src = url;
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectFit = "cover";

        wrapper.appendChild(img);

        // Insert after the "Add New" button (which is first child)
        // or just append if no button (should have button)
        state.galleryContainer.appendChild(wrapper);

        wrapper.addEventListener("click", function () {
            insertMarkdown(url);
            // Visual feedback
            wrapper.style.borderColor = "#22c55e";
            setTimeout(() => wrapper.style.borderColor = "#e5e7eb", 300);
        });
    }

    function insertMarkdown(url) {
        const markdown = `![](${url})`;
        const cmElement = document.querySelector(".CodeMirror");
        if (cmElement && cmElement.CodeMirror) {
            const doc = cmElement.CodeMirror.getDoc();
            const cursor = doc.getCursor();
            doc.replaceRange(markdown, cursor);
        } else {
            // Fallback
            const textarea = document.querySelector('textarea[name="content"]');
            if (textarea) textarea.value += "\n" + markdown;
        }
    }

    // --- Upload Logic ---
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.accept = "image/*";
    fileInput.style.display = "none";
    document.body.appendChild(fileInput);

    fileInput.addEventListener("change", function () {
        handleFiles(this.files);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }

    async function handleFiles(files) {
        if (files.length === 0) return;
        if (!state.slug) {
            alert("Пожалуйста, сначала сохраните статью, чтобы получить Slug.");
            return;
        }

        // Show loading state?
        state.galleryContainer.style.opacity = "0.5";

        try {
            const formData = new FormData();
            for (let i = 0; i < files.length; i++) {
                formData.append("files", files[i]);
            }
            formData.append("slug", state.slug);

            const response = await fetch(CONFIG.apiUpload, {
                method: "POST",
                body: formData
            });

            if (!response.ok) throw new Error("Upload failed");

            const data = await response.json();
            if (data.urls) {
                renderImages(data.urls);
            }
        } catch (error) {
            console.error(error);
            alert("Ошибка загрузки: " + error.message);
        } finally {
            state.galleryContainer.style.opacity = "1";
            fileInput.value = ""; // Reset
        }
    }

    // Run
    init();
});
