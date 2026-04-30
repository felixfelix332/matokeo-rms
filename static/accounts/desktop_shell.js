(function () {
    "use strict";

    var APP_TITLE = "Matokeo RMS";
    var loader;
    var loaderTimer;

    function keepDesktopTitle() {
        if (document.title !== APP_TITLE) {
            document.title = APP_TITLE;
        }

        var titleNode = document.querySelector("title");
        if (!titleNode || !window.MutationObserver) {
            return;
        }

        var observer = new MutationObserver(function () {
            if (document.title !== APP_TITLE) {
                document.title = APP_TITLE;
            }
        });
        observer.observe(titleNode, { childList: true, characterData: true, subtree: true });
    }

    function ensureLoader() {
        if (loader) {
            return loader;
        }

        loader = document.createElement("div");
        loader.className = "matokeo-desktop-loader";
        loader.setAttribute("aria-live", "polite");
        loader.setAttribute("aria-hidden", "true");
        loader.innerHTML = [
            '<div class="matokeo-desktop-loader-card" role="status">',
            '<div class="matokeo-desktop-loader-ring"></div>',
            '<p class="matokeo-desktop-loader-title">Loading Matokeo RMS</p>',
            '<div class="matokeo-desktop-loader-bar"></div>',
            "</div>",
        ].join("");
        document.body.appendChild(loader);
        return loader;
    }

    function showLoader() {
        window.clearTimeout(loaderTimer);
        loaderTimer = window.setTimeout(function () {
            ensureLoader().classList.add("is-visible");
            loader.setAttribute("aria-hidden", "false");
        }, 80);
    }

    function hideLoader() {
        window.clearTimeout(loaderTimer);
        if (!loader) {
            return;
        }
        loader.classList.remove("is-visible");
        loader.setAttribute("aria-hidden", "true");
    }

    function shouldShowLoaderForLink(link, event) {
        if (!link || event.defaultPrevented) {
            return false;
        }
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return false;
        }
        if (link.target && link.target !== "_self") {
            return false;
        }
        if (link.hasAttribute("download") || link.dataset.noLoader === "true") {
            return false;
        }
        var href = link.getAttribute("href") || "";
        if (!href || href.charAt(0) === "#") {
            return false;
        }
        try {
            var target = new URL(link.href, window.location.href);
            return target.origin === window.location.origin;
        } catch (error) {
            return false;
        }
    }

    function bindDesktopShell() {
        keepDesktopTitle();
        window.addEventListener("pageshow", hideLoader);
        window.addEventListener("load", hideLoader);

        document.addEventListener("click", function (event) {
            var link = event.target.closest ? event.target.closest("a[href]") : null;
            if (shouldShowLoaderForLink(link, event)) {
                showLoader();
            }
        });

        document.addEventListener("submit", function (event) {
            if (!event.defaultPrevented && !event.target.dataset.noLoader) {
                showLoader();
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bindDesktopShell);
    } else {
        bindDesktopShell();
    }
})();
