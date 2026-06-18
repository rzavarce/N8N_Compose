document.addEventListener("DOMContentLoaded", () => {
    
    // =========================================================================
    // 1. CONFIGURACIÓN E INICIALIZACIÓN DE GMAIL (VIA EMAILJS)
    // =========================================================================
    // REQUISITOS: 
    // 1. Regístrate gratis en https://www.emailjs.com/
    // 2. Conecta tu cuenta de Gmail de soporte en "Email Services".
    // 3. Crea un "Email Template" mapeando las variables {{user_name}}, {{user_email}}, etc.
    // 4. Reemplaza los siguientes strings con tus llaves reales de producción.
    
    const EMAILJS_PUBLIC_KEY = "l0Heqn_UeaaehLZl3"; 
    const EMAILJS_SERVICE_ID = "6PuzCjKeAnbVQrRbZmHl6";
    const EMAILJS_TEMPLATE_ID = "template_qffm0m7";

    // Inicializa la conexión con la API de EmailJS
    if (EMAILJS_PUBLIC_KEY !== "TU_PUBLIC_KEY_AQUI") {
        emailjs.init(EMAILJS_PUBLIC_KEY);
    }

    // =========================================================================
    // 2. CONTROL DEL FORMULARIO Y CONTROL DE FLUJO
    // =========================================================================
    const contactForm = document.getElementById("tech-contact-form");
    const submitBtn = document.getElementById("submit-btn");
    const btnText = document.getElementById("btn-text");
    const btnLoader = document.getElementById("btn-loader");
    const formResponse = document.getElementById("form-response");

    if (contactForm) {
        contactForm.addEventListener("submit", function(event) {
            event.preventDefault(); // Previene la recarga de página convencional

            // Activa interfaz visual de carga (Feedback para el usuario)
            submitBtn.disabled = true;
            btnText.textContent = "TRANSMITIENDO DATOS AL SERVIDOR...";
            btnLoader.classList.remove("hidden");
            formResponse.classList.add("hidden");

            // Encapsulación estructurada de parámetros
            const templateParams = {
                user_name: document.getElementById("user_name").value,
                user_email: document.getElementById("user_email").value,
                user_phone: document.getElementById("user_phone").value,
                service_type: document.getElementById("service_type").value,
                message: document.getElementById("message").value
            };

            // Simulación de depuración en caso de llaves genéricas
            if (EMAILJS_PUBLIC_KEY === "TU_PUBLIC_KEY_AQUI") {
                setTimeout(() => {
                    setFormResponse(
                        true, 
                        "¡Paquete simulado con éxito! Instala tus credenciales reales de EmailJS para enlazar con Gmail."
                    );
                    contactForm.reset();
                }, 1800);
                return;
            }

            // Despliegue de transmisión real hacia la API de Gmail
            emailjs.send(EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, templateParams)
                .then(function(response) {
                    console.log("TRANSMISSION SUCCESSFUL:", response.status, response.text);
                    setFormResponse(true, "¡PAQUETE DE DATOS ENVIADO! Nos pondremos en contacto a la brevedad.");
                    contactForm.reset(); // Limpia el formulario
                }, function(error) {
                    console.error("TRANSMISSION CRITICAL ERROR:", error);
                    setFormResponse(false, "ERROR DE ENLACE: Paquete rechazado por el nodo de correo. Intente vía WhatsApp.");
                });
        });
    }

    // Renderizado de mensajes informativos de respuesta
    function setFormResponse(isSuccess, message) {
        btnLoader.classList.add("hidden");
        submitBtn.disabled = false;
        btnText.innerHTML = '<i class="fa-solid fa-paper-plane"></i> TRANSMITIR REQUERIMIENTO';
        
        formResponse.textContent = message;
        formResponse.className = "form-message"; // Reset
        
        if (isSuccess) {
            formResponse.classList.add("success");
        } else {
            formResponse.classList.add("error");
        }
        formResponse.classList.remove("hidden");
    }

    // =========================================================================
    // 3. MENÚ DE NAVEGACIÓN MÓVIL COLAPSABLE
    // =========================================================================
    const mobileMenuBtn = document.getElementById("mobile-menu");
    const navLinksContainer = document.querySelector(".nav-links");

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener("click", () => {
            mobileMenuBtn.classList.toggle("is-active");
            navLinksContainer.classList.toggle("active");
        });
    }

    // Cierre adaptativo al presionar cualquier enlace móvil
    document.querySelectorAll(".nav-item").forEach(item => {
        item.addEventListener("click", () => {
            if (navLinksContainer.classList.contains("active")) {
                mobileMenuBtn.classList.remove("is-active");
                navLinksContainer.classList.remove("active");
            }
        });
    });

    // =========================================================================
    // 4. DETECCIÓN DE SECCIÓN EN TIEMPO REAL (INTERSECTION OBSERVER)
    // =========================================================================
    const sections = document.querySelectorAll('section, header');
    const navLinksElements = document.querySelectorAll('.nav-item');
    
    const observerOptions = {
        root: null,
        rootMargin: '-30% 0px -60% 0px', 
        threshold: 0
    };

    const sectionObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const currentId = entry.target.getAttribute('id');
                navLinksElements.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${currentId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, observerOptions);

    sections.forEach(section => sectionObserver.observe(section));
});