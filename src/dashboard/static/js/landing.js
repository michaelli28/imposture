(function () {
    "use strict";

    /* ---- Mobile nav toggle ---- */

    var toggle = document.getElementById("nav-toggle");
    var links = document.getElementById("nav-links");

    if (toggle && links) {
        toggle.addEventListener("click", function () {
            links.classList.toggle("open");
        });

        /* Close menu when a link is clicked */
        links.querySelectorAll("a").forEach(function (link) {
            link.addEventListener("click", function () {
                links.classList.remove("open");
            });
        });
    }

    /* ---- Sticky nav shadow on scroll ---- */

    var nav = document.getElementById("nav");
    if (nav) {
        window.addEventListener("scroll", function () {
            if (window.scrollY > 10) {
                nav.style.boxShadow = "0 2px 12px rgba(249, 115, 22, 0.08)";
            } else {
                nav.style.boxShadow = "none";
            }
        }, { passive: true });
    }
})();
