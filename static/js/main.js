


document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', function() {
            this.classList.toggle('active');
            navMenu.classList.toggle('active');
        });
        
        
        document.addEventListener('click', function(event) {
            if (!navToggle.contains(event.target) && !navMenu.contains(event.target)) {
                navToggle.classList.remove('active');
                navMenu.classList.remove('active');
            }
        });
        
        
        navMenu.querySelectorAll('a').forEach(function(link) {
            link.addEventListener('click', function() {
                navToggle.classList.remove('active');
                navMenu.classList.remove('active');
            });
        });
    }
    
    
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const dashboardSidebar = document.getElementById('dashboard-sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    
    if (sidebarToggle && dashboardSidebar) {
        sidebarToggle.addEventListener('click', function() {
            dashboardSidebar.classList.toggle('active');
            if (sidebarOverlay) {
                sidebarOverlay.classList.toggle('active');
            }
        });
        
        
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', function() {
                dashboardSidebar.classList.remove('active');
                sidebarOverlay.classList.remove('active');
            });
        }
        
        
        dashboardSidebar.querySelectorAll('.sidebar-link').forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth < 1024) {
                    dashboardSidebar.classList.remove('active');
                    if (sidebarOverlay) {
                        sidebarOverlay.classList.remove('active');
                    }
                }
            });
        });
    }

    // Show/hide password toggles (supports multiple password fields per page)
    function syncPasswordToggleVisual(btn, isHidden) {
        const showLabel = 'Show password';
        const hideLabel = 'Hide password';
        // User expectation: slash icon == hidden, plain eye == shown
        btn.setAttribute('aria-label', isHidden ? showLabel : hideLabel);
        btn.setAttribute('aria-pressed', isHidden ? 'false' : 'true');

        const eye = btn.querySelector('[data-icon="eye"]');
        const eyeOff = btn.querySelector('[data-icon="eye-off"]');
        if (eye && eyeOff) {
            // hidden => show eye-off (slash). shown => show eye.
            eye.classList.toggle('hidden', isHidden);
            eyeOff.classList.toggle('hidden', !isHidden);
        }
    }

    document.querySelectorAll('[data-password-toggle]').forEach(function(btn) {
        const targetId = btn.getAttribute('data-target');
        const input =
            (targetId && document.getElementById(targetId)) ||
            (btn.closest('.password-input-wrapper') && btn.closest('.password-input-wrapper').querySelector('input'));

        if (input) {
            syncPasswordToggleVisual(btn, input.getAttribute('type') === 'password');
        }

        btn.addEventListener('click', function() {
            const targetId2 = btn.getAttribute('data-target');
            const input2 =
                (targetId2 && document.getElementById(targetId2)) ||
                (btn.closest('.password-input-wrapper') && btn.closest('.password-input-wrapper').querySelector('input'));

            if (!input2) return;

            const isHidden = input2.getAttribute('type') === 'password';
            input2.setAttribute('type', isHidden ? 'text' : 'password');
            syncPasswordToggleVisual(btn, input2.getAttribute('type') === 'password');
        });
    });

    // Live password validation (registration)
    const pw1 = document.getElementById('id_password1');
    const pw2 = document.getElementById('id_password2');
    const rulesRoot = document.querySelector('[data-password-live-help]');
    const matchHint = document.querySelector('[data-password-match-hint]');
    const usernameInput =
        document.getElementById('id_username') || document.querySelector('input[name="username"]');
    const emailInput =
        document.getElementById('id_email') || document.querySelector('input[name="email"]');

    // Lightweight common-password list (frontend hint). Server still enforces Django's full list.
    const COMMON_PASSWORDS = new Set([
        'password', 'password1', 'password123', '123456', '12345678', '123456789', '1234567890',
        'qwerty', 'qwerty123', 'abc123', '111111', '000000', 'iloveyou', 'admin', 'admin123',
        'welcome', 'letmein', 'monkey', 'dragon', 'football', 'baseball', 'starwars', 'princess',
        'login', 'passw0rd', 'trustno1', 'sunshine', 'shadow', 'master', 'killer', 'superman',
        'batman', 'harley', 'pokemon', 'whatever', 'freedom', 'hello', 'secret', 'asdfghjkl',
        'zxcvbnm', '1q2w3e4r', '1q2w3e4r5t', 'qazwsx', 'qazwsx123',
    ]);

    function setRule(ruleName, ok) {
        if (!rulesRoot) return;
        const el = rulesRoot.querySelector('[data-rule="' + ruleName + '"]');
        if (!el) return;
        el.classList.toggle('is-valid', !!ok);
        el.classList.toggle('is-invalid', !ok);
    }

    function setMatch(ok, touched) {
        if (!matchHint) return;
        // Only show match status after user starts typing confirmation (or once pw1 has content)
        if (!touched) {
            matchHint.classList.remove('is-valid', 'is-invalid');
            return;
        }
        matchHint.classList.toggle('is-valid', !!ok);
        matchHint.classList.toggle('is-invalid', !ok);
    }

    function normalizeForCompare(s) {
        return (s || '').toString().trim().toLowerCase();
    }

    function levenshteinDistance(a, b) {
        // Small inputs only; O(n*m) is fine here.
        const s = a || '';
        const t = b || '';
        const n = s.length;
        const m = t.length;
        if (n === 0) return m;
        if (m === 0) return n;

        const dp = new Array(m + 1);
        for (let j = 0; j <= m; j++) dp[j] = j;

        for (let i = 1; i <= n; i++) {
            let prev = dp[0];
            dp[0] = i;
            for (let j = 1; j <= m; j++) {
                const tmp = dp[j];
                const cost = s[i - 1] === t[j - 1] ? 0 : 1;
                dp[j] = Math.min(
                    dp[j] + 1,      // deletion
                    dp[j - 1] + 1,  // insertion
                    prev + cost     // substitution
                );
                prev = tmp;
            }
        }
        return dp[m];
    }

    function similarityRatio(a, b) {
        const s = normalizeForCompare(a);
        const t = normalizeForCompare(b);
        const maxLen = Math.max(s.length, t.length);
        if (maxLen === 0) return 0;
        const dist = levenshteinDistance(s, t);
        return 1 - dist / maxLen;
    }

    function isTooSimilarToUserInfo(password, username, email) {
        const p = normalizeForCompare(password);
        const u = normalizeForCompare(username);
        const e = normalizeForCompare(email);
        const local = e.includes('@') ? e.split('@')[0] : e;

        // Substring checks (most intuitive for users)
        const tokens = [];
        if (u.length >= 3) tokens.push(u);
        if (local.length >= 3) tokens.push(local);
        if (e.length >= 3) tokens.push(e);

        for (const tok of tokens) {
            if (tok && p.includes(tok)) return true;
        }

        // Edit-distance similarity checks (catch minor variations)
        const THRESHOLD = 0.75;
        if (u.length >= 4 && similarityRatio(p, u) >= THRESHOLD) return true;
        if (local.length >= 4 && similarityRatio(p, local) >= THRESHOLD) return true;
        return false;
    }

    function updatePasswordLive() {
        if (!pw1) return;
        const v = pw1.value || '';
        const vLower = normalizeForCompare(v);

        setRule('length', v.length >= 12);
        setRule('letter', /[A-Za-z]/.test(v));
        setRule('digit', /\d/.test(v));
        setRule('special', /[^A-Za-z0-9]/.test(v));
        setRule('numeric_only', v.length > 0 && !/^\d+$/.test(v));
        setRule('common', v.length > 0 && !COMMON_PASSWORDS.has(vLower));

        const username = usernameInput ? usernameInput.value : '';
        const email = emailInput ? emailInput.value : '';
        const similarityOk = v.length > 0 ? !isTooSimilarToUserInfo(v, username, email) : false;
        setRule('similarity', similarityOk);

        if (pw2) {
            const touched = (pw2.value || '').length > 0 || v.length > 0;
            setMatch(v.length > 0 && pw2.value === v, touched);
        }
    }

    if (pw1) {
        pw1.addEventListener('input', updatePasswordLive);
        pw1.addEventListener('blur', updatePasswordLive);
    }
    if (pw2) {
        pw2.addEventListener('input', updatePasswordLive);
        pw2.addEventListener('blur', updatePasswordLive);
    }
    if (usernameInput) {
        usernameInput.addEventListener('input', updatePasswordLive);
        usernameInput.addEventListener('blur', updatePasswordLive);
    }
    if (emailInput) {
        emailInput.addEventListener('input', updatePasswordLive);
        emailInput.addEventListener('blur', updatePasswordLive);
    }
    updatePasswordLive();
});

