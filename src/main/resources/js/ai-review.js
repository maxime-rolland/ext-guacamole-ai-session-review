/*
 * AI Session Review — client-side glue.
 *
 * Le manifest expose ce fichier dans /app.js. Au chargement, on récupère
 * les services Angular de Guacamole et on installe sur $rootScope un
 * objet `aiReview` que les patches HTML (menu user + modale) référencent.
 *
 * On évite d'enregistrer un nouveau module Angular : à ce stade la
 * webapp est déjà bootstrapée, et tout block .config/.run additionnel
 * serait ignoré. On utilise l'injector existant.
 */
(function () {

    function init() {

        var appEl = document.querySelector('[ng-app]');
        if (!appEl || !window.angular) {
            return setTimeout(init, 100);
        }

        var injector = angular.element(appEl).injector();
        if (!injector) {
            return setTimeout(init, 100);
        }

        var $rootScope            = injector.get('$rootScope');
        var requestService        = injector.get('requestService');
        var authenticationService = injector.get('authenticationService');

        var state = {
            visible:   false,
            loading:   false,
            error:     null,
            summaries: [],
            selected:  null,
            events:    []
        };

        function apiGet(path) {
            return requestService({
                method: 'GET',
                url:    'api/session/ext/ai-session-review/' + path,
                params: { token: authenticationService.getCurrentToken() }
            });
        }

        state.open = function open() {
            state.visible  = true;
            state.loading  = true;
            state.error    = null;
            state.selected = null;
            state.events   = [];
            apiGet('summaries').then(
                function (data) {
                    state.summaries = data || [];
                    state.loading   = false;
                },
                function (err) {
                    state.error   = (err && (err.message || err.statusText)) || 'Erreur réseau';
                    state.loading = false;
                }
            );
        };

        state.close = function close() {
            state.visible  = false;
            state.selected = null;
            state.events   = [];
        };

        state.select = function select(summary) {
            state.selected = summary;
            state.events   = [];
            apiGet('summaries/' + encodeURIComponent(summary.historyUuid) + '/events').then(
                function (data) { state.events = data || []; }
            );
        };

        state.deselect = function deselect() {
            state.selected = null;
            state.events   = [];
        };

        $rootScope.aiReview = state;

        // Annonce la mise à jour à Angular (on est hors du digest cycle ici)
        if (!$rootScope.$$phase) {
            $rootScope.$apply();
        }
    }

    init();

}());
