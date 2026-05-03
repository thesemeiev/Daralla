(function () {
    function create(deps) {
        deps = deps || {};
        var getCurrentPage = typeof deps.getCurrentPage === 'function'
            ? deps.getCurrentPage
            : function () { return window.currentPage; };
        var getTheme = typeof deps.getTheme === 'function'
            ? deps.getTheme
            : function () { return (typeof window.getTheme === 'function' ? window.getTheme() : 'dark'); };

        var aboutPageState = null;

        function initAboutPage() {
            if (aboutPageState && aboutPageState.disposed) aboutPageState = null;
            var pageEl = document.getElementById('page-about');
            var wrapEl = document.getElementById('about-hero-canvas-wrap');
            if (!pageEl || !wrapEl) return;

            document.body.classList.add('about-page-active');
            var targetProgress = 0;
            var scrollListener = function () {
                if (getCurrentPage() !== 'about') return;
                var scrollTop = window.scrollY || document.documentElement.scrollTop;
                var maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
                targetProgress = Math.min(1, Math.max(0, scrollTop / maxScroll));
            };
            var getTargetProgress = function () {
                var scrollTop = window.scrollY || document.documentElement.scrollTop;
                var maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
                return Math.min(1, Math.max(0, scrollTop / maxScroll));
            };

            var observer = new IntersectionObserver(
                function (entries) {
                    entries.forEach(function (e) {
                        if (e.isIntersecting) e.target.classList.add('in-view');
                    });
                },
                { root: null, rootMargin: '0px 0px -12% 0px', threshold: 0.15 }
            );
            pageEl.querySelectorAll('.about-reveal').forEach(function (el) { observer.observe(el); });
            pageEl.querySelectorAll('.about-contact-card').forEach(function (el) { observer.observe(el); });
            var heroEl = pageEl.querySelector('.about-hero');
            if (heroEl) heroEl.classList.add('in-view');

            var smoothedProgress = 0;
            aboutPageState = {
                scrollListener: scrollListener,
                observer: observer,
                disposed: false,
                renderer: null,
                resizeHandler: null,
                animId: null,
                smoothedProgress: 0
            };
            window.addEventListener('scroll', scrollListener, { passive: true });
            scrollListener();
            aboutPageState.animId = requestAnimationFrame(animate);

            var isTouchDevice = typeof window !== 'undefined' && ('ontouchstart' in window || (navigator && navigator.maxTouchPoints > 0));
            var lerpFactor = isTouchDevice ? 0.028 : 0.06;
            function animate() {
                if (!aboutPageState || aboutPageState.disposed) return;
                aboutPageState.animId = requestAnimationFrame(animate);
                targetProgress = getTargetProgress();
                var t = lerpFactor;
                smoothedProgress += (targetProgress - smoothedProgress) * t;
                aboutPageState.smoothedProgress = smoothedProgress;
                var themeLight = getTheme() === 'light';
                var isLight = themeLight ? (smoothedProgress < 0.5) : (smoothedProgress > 0.5);
                document.body.style.backgroundColor = isLight ? '#f0f0f2' : '#131314';
                pageEl.classList.toggle('about-bg-light', isLight);
                if (aboutPageState.mesh) {
                    var grp = aboutPageState.mesh;
                    grp.rotation.y = smoothedProgress * Math.PI * 2;
                    grp.rotation.x = smoothedProgress * Math.PI * 0.5;
                    var time = performance.now() * 0.001;
                    var reducedMotion = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                    var breatheAmp = reducedMotion ? 0 : 0.028;
                    if (aboutPageState.aboutNodeBases) {
                        aboutPageState.aboutNodeBases.forEach(function (item) {
                            var m = item.mesh;
                            var b = item.base;
                            var ph = item.phase;
                            m.position.set(
                                b.x + Math.sin(time * 0.35 + ph) * breatheAmp,
                                b.y + Math.cos(time * 0.28 + ph * 1.3) * breatheAmp,
                                b.z + Math.sin(time * 0.31 + ph * 0.7) * breatheAmp * 0.75
                            );
                        });
                    }
                    if (aboutPageState.aboutNodeMeshes && aboutPageState.aboutEdgePairs && aboutPageState.aboutEdgeGeoms) {
                        var nodes = aboutPageState.aboutNodeMeshes;
                        aboutPageState.aboutEdgeGeoms.forEach(function (geo, ei) {
                            var pair = aboutPageState.aboutEdgePairs[ei];
                            var p0 = nodes[pair[0]].position;
                            var p1 = nodes[pair[1]].position;
                            var arr = geo.attributes.position.array;
                            arr[0] = p0.x;
                            arr[1] = p0.y;
                            arr[2] = p0.z;
                            arr[3] = p1.x;
                            arr[4] = p1.y;
                            arr[5] = p1.z;
                            geo.attributes.position.needsUpdate = true;
                        });
                    }
                    if (aboutPageState.aboutEdgeMaterials) {
                        var p = smoothedProgress;
                        aboutPageState.aboutEdgeMaterials.forEach(function (mat, i) {
                            mat.opacity = 0.16 + p * 0.22 + Math.sin(time * 0.85 + i * 0.65) * 0.032;
                        });
                    }
                    if (aboutPageState.aboutNodeMaterial && aboutPageState.aboutNodeMaterial.envMapIntensity !== undefined) {
                        aboutPageState.aboutNodeMaterial.envMapIntensity = 0.78 + smoothedProgress * 0.05;
                    }
                    if (aboutPageState.aboutNodeMaterial && aboutPageState.threeRef && aboutPageState._nodeColA) {
                        var pCol = Math.min(0.48, smoothedProgress * 0.92);
                        aboutPageState.aboutNodeMaterial.color.copy(aboutPageState._nodeColA).lerp(aboutPageState._nodeColB, pCol);
                        aboutPageState.aboutNodeMaterial.emissive.copy(aboutPageState._nodeEmA).lerp(aboutPageState._nodeEmB, pCol * 0.55);
                        if (aboutPageState.aboutEdgeMaterials) {
                            aboutPageState.aboutEdgeMaterials.forEach(function (mat) {
                                mat.color.copy(aboutPageState._edgeColA).lerp(aboutPageState._edgeColB, pCol);
                            });
                        }
                    }
                }
                if (aboutPageState.lights) {
                    var k = 1;
                    aboutPageState.lights.ambient.intensity = 0.58 * k;
                    aboutPageState.lights.dirLight.intensity = 1.15 * k;
                    aboutPageState.lights.rimLight.intensity = 0.8 * k;
                    aboutPageState.lights.fillLight.intensity = 0.4 * k;
                    aboutPageState.lights.highlight1.intensity = 1.1 * k;
                    aboutPageState.lights.highlight2.intensity = 0.6 * k;
                }
                if (aboutPageState.renderer && aboutPageState.scene && aboutPageState.camera) {
                    aboutPageState.renderer.render(aboutPageState.scene, aboutPageState.camera);
                }
            }

            import('three').then(function (THREE) {
                if (getCurrentPage() !== 'about' || !aboutPageState || aboutPageState.disposed || !wrapEl.parentNode) return;
                if (!THREE || !THREE.Scene) return;
                var canvas = document.createElement('canvas');
                wrapEl.innerHTML = '';
                wrapEl.appendChild(canvas);
                var scene = new THREE.Scene();
                var camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1000);
                camera.position.z = 4;
                var renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
                renderer.setSize(window.innerWidth, window.innerHeight);
                renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                renderer.setClearColor(0x000000, 0);
                if (renderer.outputColorSpace !== undefined) renderer.outputColorSpace = THREE.SRGBColorSpace;
                else if (renderer.outputEncoding !== undefined) renderer.outputEncoding = THREE.sRGBEncoding;
                var ambient = new THREE.AmbientLight(0x3a3a42, 0.55);
                scene.add(ambient);
                var dirLight = new THREE.DirectionalLight(0xf2f2f5, 1.05);
                dirLight.position.set(3, 4, 5);
                scene.add(dirLight);
                var rimLight = new THREE.DirectionalLight(0xd8d8e0, 0.55);
                rimLight.position.set(-4, -2, -3);
                scene.add(rimLight);
                var fillLight = new THREE.DirectionalLight(0x9898a2, 0.35);
                fillLight.position.set(-2, 1, 3);
                scene.add(fillLight);
                var highlightLight = new THREE.PointLight(0xffffff, 0.95, 8);
                highlightLight.position.set(2, 2, 2);
                scene.add(highlightLight);
                var highlightLight2 = new THREE.PointLight(0xe4e4ea, 0.5, 6);
                highlightLight2.position.set(-2.5, 1.5, 2);
                scene.add(highlightLight2);
                if (aboutPageState) {
                    aboutPageState.lights = {
                        ambient: ambient,
                        dirLight: dirLight,
                        rimLight: rimLight,
                        fillLight: fillLight,
                        highlight1: highlightLight,
                        highlight2: highlightLight2
                    };
                }
                var networkGroup = new THREE.Group();
                var nodeMat = new THREE.MeshStandardMaterial({
                    color: 0x2a2b30,
                    metalness: 0.45,
                    roughness: 0.38,
                    emissive: 0x0c0c10,
                    emissiveIntensity: 0.12,
                    envMapIntensity: 0.85
                });
                var nodeDefs = [
                    { x: 0, y: 0.05, z: 0, r: 0.11 },
                    { x: -0.95, y: 0.32, z: 0.18, r: 0.065 },
                    { x: 0.88, y: -0.22, z: 0.12, r: 0.07 },
                    { x: 0.12, y: 0.78, z: -0.22, r: 0.062 },
                    { x: -0.42, y: -0.48, z: 0.28, r: 0.058 },
                    { x: 0.52, y: 0.38, z: -0.58, r: 0.06 },
                    { x: -0.32, y: 0.15, z: 0.68, r: 0.055 }
                ];
                var aboutNodeMeshes = [];
                var aboutNodeBases = [];
                nodeDefs.forEach(function (d, i) {
                    var sg = new THREE.SphereGeometry(d.r, 22, 18);
                    var sphere = new THREE.Mesh(sg, nodeMat);
                    sphere.position.set(d.x, d.y, d.z);
                    networkGroup.add(sphere);
                    aboutNodeMeshes.push(sphere);
                    aboutNodeBases.push({
                        mesh: sphere,
                        base: new THREE.Vector3(d.x, d.y, d.z),
                        phase: i * 0.85
                    });
                });
                var aboutEdgePairs = [[0, 1], [0, 2], [0, 3], [0, 4], [1, 5], [2, 6], [3, 5]];
                var aboutEdgeGeoms = [];
                var aboutEdgeMaterials = [];
                aboutEdgePairs.forEach(function (pair) {
                    var a = aboutNodeMeshes[pair[0]].position;
                    var b = aboutNodeMeshes[pair[1]].position;
                    var edgeGeo = new THREE.BufferGeometry().setFromPoints([a.clone(), b.clone()]);
                    var lmat = new THREE.LineBasicMaterial({
                        color: 0x7a7a86,
                        transparent: true,
                        opacity: 0.22,
                        depthWrite: false
                    });
                    networkGroup.add(new THREE.Line(edgeGeo, lmat));
                    aboutEdgeGeoms.push(edgeGeo);
                    aboutEdgeMaterials.push(lmat);
                });
                networkGroup.scale.setScalar(1.2);
                scene.add(networkGroup);
                (function setDefaultEnvMap() {
                    var size = 64;
                    var canvases = [];
                    for (var i = 0; i < 6; i++) {
                        var c = document.createElement('canvas');
                        c.width = size;
                        c.height = size;
                        var ctx = c.getContext('2d');
                        var g = ctx.createLinearGradient(0, 0, size, size);
                        g.addColorStop(0, '#0a0a0c');
                        g.addColorStop(0.5, '#1a1a1e');
                        g.addColorStop(1, '#2e2e34');
                        ctx.fillStyle = g;
                        ctx.fillRect(0, 0, size, size);
                        canvases.push(c);
                    }
                    var cubeEnv = new THREE.CubeTexture(canvases);
                    cubeEnv.mapping = THREE.CubeReflectionMapping;
                    cubeEnv.needsUpdate = true;
                    scene.environment = cubeEnv;
                })();
                (function loadEnvMapHDR() {
                    import('https://unpkg.com/three@0.160.0/examples/jsm/loaders/RGBELoader.js').then(function (mod) {
                        var RGBELoader = mod.default;
                        var rl = new RGBELoader();
                        rl.load('https://dl.polyhaven.org/file/ahjdyrye/industrial_sunset_puresky_2k.hdr', function (hdr) {
                            if (!aboutPageState || aboutPageState.disposed) return;
                            var pmrem = new THREE.PMREMGenerator(renderer);
                            var envMap = pmrem.fromEquirectangular(hdr).texture;
                            scene.environment = envMap;
                            hdr.dispose();
                            pmrem.dispose();
                        }, undefined, function () {});
                    }).catch(function () {});
                })();
                var lastResizeW = 0;
                var resizeDebounce = null;
                var RESIZE_THRESHOLD = 10;
                function onResize() {
                    if (!aboutPageState || aboutPageState.disposed) return;
                    var w = window.innerWidth;
                    var h = window.innerHeight;
                    if (resizeDebounce) clearTimeout(resizeDebounce);
                    resizeDebounce = setTimeout(function () {
                        resizeDebounce = null;
                        if (!aboutPageState || aboutPageState.disposed) return;
                        var widthChanged = Math.abs(w - lastResizeW) > RESIZE_THRESHOLD;
                        if (widthChanged || lastResizeW === 0) {
                            lastResizeW = w;
                            camera.aspect = w / h;
                            camera.updateProjectionMatrix();
                            renderer.setSize(w, h);
                        }
                    }, 280);
                }
                lastResizeW = window.innerWidth;
                window.addEventListener('resize', onResize);
                aboutPageState.renderer = renderer;
                aboutPageState.scene = scene;
                aboutPageState.camera = camera;
                aboutPageState.mesh = networkGroup;
                aboutPageState.aboutNodeMeshes = aboutNodeMeshes;
                aboutPageState.aboutNodeBases = aboutNodeBases;
                aboutPageState.aboutNodeMaterial = nodeMat;
                aboutPageState.aboutEdgePairs = aboutEdgePairs;
                aboutPageState.aboutEdgeGeoms = aboutEdgeGeoms;
                aboutPageState.aboutEdgeMaterials = aboutEdgeMaterials;
                aboutPageState.resizeHandler = onResize;
                aboutPageState.threeRef = THREE;
                aboutPageState._nodeColA = new THREE.Color(0x26262c);
                aboutPageState._nodeColB = new THREE.Color(0x6e6e78);
                aboutPageState._nodeEmA = new THREE.Color(0x060608);
                aboutPageState._nodeEmB = new THREE.Color(0x121214);
                aboutPageState._edgeColA = new THREE.Color(0x5c5c66);
                aboutPageState._edgeColB = new THREE.Color(0x7a7a84);
                aboutPageState.animId = requestAnimationFrame(animate);
            }).catch(function () {});
        }

        function aboutPageDispose() {
            if (!aboutPageState) return;
            aboutPageState.disposed = true;
            if (aboutPageState.animId) cancelAnimationFrame(aboutPageState.animId);
            window.removeEventListener('scroll', aboutPageState.scrollListener);
            if (aboutPageState.resizeHandler) window.removeEventListener('resize', aboutPageState.resizeHandler);
            if (aboutPageState.observer) aboutPageState.observer.disconnect();
            if (aboutPageState.renderer) {
                aboutPageState.renderer.dispose();
                if (aboutPageState.renderer.domElement && aboutPageState.renderer.domElement.parentNode) {
                    aboutPageState.renderer.domElement.parentNode.removeChild(aboutPageState.renderer.domElement);
                }
            }
            var wrapEl = document.getElementById('about-hero-canvas-wrap');
            if (wrapEl) wrapEl.innerHTML = '';
            var pageEl = document.getElementById('page-about');
            if (pageEl) pageEl.classList.remove('about-bg-light');
            document.body.classList.remove('about-page-active');
            document.body.style.backgroundColor = '';
            aboutPageState = null;
        }

        return {
            initAboutPage: initAboutPage,
            aboutPageDispose: aboutPageDispose
        };
    }

    window.DarallaAboutSceneFeature = { create: create };
})();
