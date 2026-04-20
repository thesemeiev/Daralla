(function () {
    function createInstructionsModalFeature(deps) {
        var _deps = deps || {};

        function showInstructionModal(platform) {
            _deps.setCurrentInstructionPlatform(platform);
            _deps.setCurrentInstructionStep(0);
            var instruction = _deps.getInstructionStepsMap()[platform];
            if (!instruction) return;
            _deps.setCurrentInstructionSteps(instruction.steps);
            document.getElementById('instruction-modal-title').textContent = instruction.title;
            document.getElementById('instruction-modal').style.display = 'flex';
            renderInstructionStep();
        }

        function renderInstructionStep() {
            var steps = _deps.getCurrentInstructionSteps();
            var stepIndex = _deps.getCurrentInstructionStep();
            var container = document.getElementById('instruction-steps-container');
            var step = steps[stepIndex];
            if (!step || !container) return;
            container.innerHTML = '\n'
                + '        <div class="instruction-step-box">\n'
                + '            <h3 class="instruction-step-title">' + step.title + '</h3>\n'
                + '            <div class="instruction-step-body">\n'
                + '                ' + step.content + '\n'
                + '            </div>\n'
                + '        </div>\n'
                + '    ';
            document.getElementById('instruction-step-indicator').textContent = 'Шаг ' + (stepIndex + 1) + ' из ' + steps.length;
            var prevBtn = document.getElementById('instruction-prev-btn');
            var nextBtn = document.getElementById('instruction-next-btn');
            var closeBtn = document.getElementById('instruction-close-btn');
            if (prevBtn) prevBtn.style.display = stepIndex > 0 ? 'block' : 'none';
            if (nextBtn && closeBtn) {
                if (stepIndex === steps.length - 1) {
                    nextBtn.style.display = 'none';
                    closeBtn.style.display = 'block';
                } else {
                    nextBtn.style.display = 'block';
                    closeBtn.style.display = 'none';
                }
            }
        }

        function nextInstructionStep() {
            var stepIndex = _deps.getCurrentInstructionStep();
            var steps = _deps.getCurrentInstructionSteps();
            if (stepIndex < steps.length - 1) {
                _deps.setCurrentInstructionStep(stepIndex + 1);
                renderInstructionStep();
            }
        }

        function prevInstructionStep() {
            var stepIndex = _deps.getCurrentInstructionStep();
            if (stepIndex > 0) {
                _deps.setCurrentInstructionStep(stepIndex - 1);
                renderInstructionStep();
            }
        }

        function closeInstructionModal() {
            document.getElementById('instruction-modal').style.display = 'none';
            _deps.setCurrentInstructionPlatform(null);
            _deps.setCurrentInstructionStep(0);
            _deps.setCurrentInstructionSteps([]);
        }

        return {
            showInstructionModal: showInstructionModal,
            renderInstructionStep: renderInstructionStep,
            nextInstructionStep: nextInstructionStep,
            prevInstructionStep: prevInstructionStep,
            closeInstructionModal: closeInstructionModal
        };
    }

    window.DarallaInstructionsModalFeature = window.DarallaInstructionsModalFeature || {};
    window.DarallaInstructionsModalFeature.create = createInstructionsModalFeature;
})();
