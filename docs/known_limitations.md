# Known limitations and verification still required

* **Synthetic data only.** Parameters (arrival rates, durations, distances, walk limits, emission factors) are illustrative, not calibrated to any real car park.
* One destination per car park; no cruising between car parks; drivers have fixed walk limits; no pricing, reservations, learning or decentralised negotiation.
* Coordinated weights are not optimised; sensitivity analysis of weights is future work.
* Emission proxy is a simple assumption-based estimate; it ignores walking, approach trips and vehicle mix.
* Statistical tests on simulated replications are descriptive; p-values depend on replication count.
* Only the first replication stores a full decision log.
* **Windows `.bat` files were NOT run on native Windows** (built and checked in a Linux container). The Python commands they call were run on Linux. Please run `CHECK_ENVIRONMENT.bat`, `INSTALL.bat`, `RUN_TESTS.bat` once on your PC. See installation_troubleshooting.md.
* Dependencies were tested together on Python 3.13 (Linux). Python 3.10–3.13 should work but only 3.13 was tested.
* Streamlit's auto-play uses a 1-second timer; very slow machines may lag.
* The literature review has not been done here; sources_verification.md lists what was and was not verified.
