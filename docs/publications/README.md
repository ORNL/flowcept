
### Flowcept Papers

Bibtex is available below.

---

**Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability**  
R. Souza, T. J. Skluzacek, S. R. Wilkinson, M. Ziatdinov, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Limassol, Cyprus, 2023.  
doi: [10.1109/e-Science58273.2023.10254822](https://doi.org/10.1109/e-Science58273.2023.10254822)  
PDF: https://arxiv.org/pdf/2308.09004.pdf  

---

**PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows**  
R. Souza, A. Gueroudji, S. DeWitt, D. Rosendo, T. Ghosal, R. Ross, P. Balaprakash, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Chicago, USA., 2025.  
Publisher: IEEE.  
PDF: https://arxiv.org/pdf/2508.02866  

---

**Workflow Provenance in the Computing Continuum for Responsible, Trustworthy, and Energy-Efficient AI**  
R. Souza, S. Caino-Lores, M. Coletti, T. J. Skluzacek, A. Costan, F. Suter, M. Mattoso, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Osaka, Japan, 2024.  
doi: [10.1109/e-Science62913.2024.10678731](https://doi.org/10.1109/e-Science62913.2024.10678731)  
PDF: https://hal.science/hal-04902079v1/document  

---

**LLM Agents for Interactive Workflow Provenance: Reference Architecture and Evaluation Methodology**  
R. Souza, T. Poteet, B. Etz, D. Rosendo, A. Gueroudji, W. Shin, P. Balaprakash, and R. Ferreira da Silva,  
*Workflows in Support of Large-Scale Science (WORKS) co-located with the ACM/IEEE International Conference for High Performance Computing, Networking, Storage, and Analysis (SC)*, St. Louis, USA, 2025.  
doi: [10.1145/3731599.3767582](https://doi.org/10.1145/3731599.3767582)  

### Bixtex

```
@inproceedings{souza2023towards,
  title={Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability},
  author={Souza, Renan and Skluzacek, Tyler J and Wilkinson, Sean R and Ziatdinov, Maxim and da Silva, Rafael Ferreira},
  booktitle={IEEE International Conference on e-Science},
  doi={10.1109/e-Science58273.2023.10254822},
  url={https://doi.org/10.1109/e-Science58273.2023.10254822},
  pdf={https://arxiv.org/pdf/2308.09004.pdf},
  year={2023},
  abstract={Modern large-scale scientific discovery requires multidisciplinary collaboration across diverse computing facilities, including High Performance Computing (HPC) machines and the Edge-to-Cloud continuum. Integrated data analysis plays a crucial role in scientific discovery, especially in the current AI era, by enabling Responsible AI development, FAIR, Reproducibility, and User Steering. However, the heterogeneous nature of science poses challenges such as dealing with multiple supporting tools, cross-facility environments, and efficient HPC execution. Building on data observability, adapter system design, and provenance, we propose MIDA: an approach for lightweight runtime Multi-workflow Integrated Data Analysis. MIDA defines data observability strategies and adaptability methods for various parallel systems and machine learning tools. With observability, it intercepts the dataflows in the background without requiring instrumentation while integrating domain, provenance, and telemetry data at runtime into a unified database ready for user steering queries. We conduct experiments showing end-to-end multi-workflow analysis integrating data from Dask and MLFlow in a real distributed deep learning use case for materials science that runs on multiple environments with up to 276 GPUs in parallel. We show near-zero overhead running up to 100,000 tasks on 1,680 CPU cores on the Summit supercomputer.}
}

```

```latex
@inproceedings{souza_prov_agent_2025,
  author    = {Renan Souza and Amal Gueroudji and Stephen DeWitt and Daniel Rosendo and Tirthankar Ghosal and Robert Ross and Prasanna Balaprakash and Rafael Ferreira da Silva},
  title     = {PROV-AGENT: Unified Provenance for Tracking {AI} Agent Interactions in Agentic Workflows},
  booktitle = {IEEE International Conference on e-Science},
  year      = {2025},
  pdf = {https://arxiv.org/pdf/2508.02866},
  publisher = {IEEE},
  keywords = {Workflows, Agentic Workflows, Provenance, Lineage, Responsible AI, LLM, Agentic AI},
  abstract = {Large Language Models (LLMs) and other foundation models are increasingly used as the core of AI agents. In agentic workflows, these agents plan tasks, interact with humans and peers, and influence scientific outcomes across federated and heterogeneous environments. However, agents can hallucinate or reason incorrectly, propagating errors when one agent's output becomes another's input. Thus, assuring that agents' actions are transparent, traceable, reproducible, and reliable is critical to assess hallucination risks and mitigate their workflow impacts. While provenance techniques have long supported these principles, existing methods fail to capture and relate agent-centric metadata such as prompts, responses, and decisions with the broader workflow context and downstream outcomes. In this paper, we introduce PROV-AGENT, a provenance model that extends W3C PROV and leverages the Model Context Protocol (MCP) and data observability to integrate agent interactions into end-to-end workflow provenance. Our contributions include: (1) a provenance model tailored for agentic workflows, (2) a near real-time, open-source system for capturing agentic provenance, and (3) a cross-facility evaluation spanning edge, cloud, and HPC environments, demonstrating support for critical provenance queries and agent reliability analysis.}
}
```

```latex
@inproceedings{souza_rtai_2024,
  author    = {Renan Souza and Silvina Caino-Lores and Mark Coletti and Tyler J. Skluzacek and Alexandru Costan and Frederic Suter and Marta Mattoso and Rafael Ferreira da Silva},
  title     = {Workflow Provenance in the Computing Continuum for Responsible, Trustworthy, and Energy-Efficient {AI}},
  booktitle = {IEEE International Conference on e-Science},
  year      = {2024},
  location  = {Osaka, Japan},
  doi = {https://doi.org/10.1109/e-Science62913.2024.10678731},
  pdf = {https://hal.science/hal-04902079v1/document},
  publisher = {IEEE},
  keywords = {Artificial Intelligence, Provenance, Machine Learning, AI workflows, ML workflows, Responsible AI, Trustworthy AI, Reproducibility, AI Lifecycle, Energy-efficient AI},
  abstract = {As Artificial Intelligence (AI) becomes more pervasive in our society, it is crucial to develop, deploy, and assess Responsible and Trustworthy AI (RTAI) models, i.e., those that consider not only accuracy but also other aspects, such as explainability, fairness, and energy efficiency. Workflow provenance data have historically enabled critical capabilities towards RTAI. Provenance data derivation paths contribute to responsible workflows through transparency in tracking artifacts and resource consumption. Provenance data are well-known for their trustworthiness, helping explainability, reproducibility, and accountability. However, there are complex challenges to achieving RTAI, which are further complicated by the heterogeneous infrastructure in the computing continuum (Edge-Cloud-HPC) used to develop and deploy models. As a result, a significant research and development gap remains between workflow provenance data management and RTAI. In this paper, we present a vision of the pivotal role of workflow provenance in supporting RTAI and discuss related challenges. We present a schematic view of the relationship between RTAI and provenance, and highlight open research directions.}
}
```

```latex
@inproceedings{souza_llm_agents_works_sc25,
  title     = {{LLM} Agents for Interactive Workflow Provenance: Reference Architecture and Evaluation Methodology},
  author    = {Souza, Renan and Poteet, Timothy and Etz, Brian and Rosendo, Daniel and Gueroudji, Amal and others},
  booktitle = {Workflows in Support of Large-Scale Science ({WORKS}) co-located with the {ACM}/{IEEE} International Conference for High Performance Computing, Networking, Storage, and Analysis ({SC})},
  year      = {2025},
  address   = {St Louis, MO, USA},
  doi       = {10.1145/3731599.3767582},
  keywords  = {scientific workflows, provenance, LLM agents, Large language models, AI agents, agentic workflows, agentic provenance}
}
```
