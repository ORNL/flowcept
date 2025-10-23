
### Flowcept Papers

Bibtex is available below.

---

**Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability**  
R. Souza, T. J. Skluzacek, S. R. Wilkinson, M. Ziatdinov, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Limassol, Cyprus, 2023.  <br/>
**About**: Introduces Flowcept’s lightweight runtime provenance and data observability architecture and shows minimal-intrusion capture across heterogeneous workflows. <br/>
[[doi]](https://doi.org/10.1109/e-Science58273.2023.10254822)
[[pdf]](https://arxiv.org/pdf/2308.09004.pdf)  
---

**PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows**  
R. Souza, A. Gueroudji, S. DeWitt, D. Rosendo, T. Ghosal, R. Ross, P. Balaprakash, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Chicago, USA., 2025. <br/>
**About**: Defines agentic provenance and a unified provenance model and tooling to capture, link, and query AI-agent interactions within agentic workflows. </br>
[[doi]](https://doi.org/10.1109/eScience65000.2025.00093) 
[[pdf]](https://arxiv.org/pdf/2508.02866)
[[html]](https://arxiv.org/html/2508.02866v3) <br/>


---

**Workflow Provenance in the Computing Continuum for Responsible, Trustworthy, and Energy-Efficient AI**  
R. Souza, S. Caino-Lores, M. Coletti, T. J. Skluzacek, A. Costan, F. Suter, M. Mattoso, and R. Ferreira da Silva,  
*IEEE International Conference on e-Science*, Osaka, Japan, 2024. <br/>
**About**: Explains how end-to-end provenance across edge, cloud, and HPC supports responsible, trustworthy, and energy-aware AI workflows. <br/>
[[doi]](https://doi.org/10.1109/e-Science62913.2024.10678731) 
[[pdf]](https://hal.science/hal-04902079v1/document) <br/>


---

**LLM Agents for Interactive Workflow Provenance: Reference Architecture and Evaluation Methodology**  
R. Souza, T. Poteet, B. Etz, D. Rosendo, A. Gueroudji, W. Shin, P. Balaprakash, and R. Ferreira da Silva,  
*Workflows in Support of Large-Scale Science (WORKS) co-located with the ACM/IEEE International Conference for High Performance Computing, Networking, Storage, and Analysis (SC)*, St. Louis, USA, 2025.  
**About**: Presents a reference architecture and evaluation method for LLM agents that query and act on large-scale provenance databases. </br>
[[doi]](https://doi.org/10.1145/3731599.3767582) 
[[pdf]](https://arxiv.org/pdf/2509.13978)
[[html]](https://arxiv.org/html/2509.13978)


--- 

### Papers that used Flowcept


**Toward a Persistent Event-Streaming System for High-Performance Computing Applications**
M. Dorier, A. Gueroudji, V. Hayot-Sasson, H. Nguyen, S. Ockerman, R. Souza, T. Bicer, H. Pan, P. Carns, K. Chard, and others
*Frontiers in High Performance Computing*, 2025. <br/>
**About**: Demonstrates Flowcept generating high-volume provenance that is persistently streamed with Mofka for HPC applications. <br/>
[[doi]](https://doi.org/10.3389/fhpcp.2025.1638203) 
[[pdf]](https://web.cels.anl.gov/~woz/papers/Mofka_2025.pdf) 
[[html]](https://www.frontiersin.org/journals/high-performance-computing/articles/10.3389/fhpcp.2025.1638203/full)
<br/>


---

**AI Agents for Enabling Autonomous Experiments at ORNL’s HPC and Manufacturing User Facilities**
D. Rosendo, S. DeWitt, R. Souza, P. Austria, T. Ghosal, M. McDonnell, R. Miller, T. Skluzacek, J. Haley, B. Turcksin, and others
*Extreme-Scale Experiment-in-the-Loop Computing (XLOOP) co-located with the ACM/IEEE International Conference for High Performance Computing, Networking, Storage, and Analysis (SC)*, 2025. <br/>
**About**: Leverages Flowcept’s agentic provenance to coordinate multi-agent experiments and connect agents with HPC simulations through a shared provenance stream. <br/>
[[doi]](https://doi.org/10.1145/3731599.3767592)
[[pdf]](https://rafaelsilva.com/files/publications/rosendo2025xloop.pdf)
[[html]](https://camps.aptaracorp.com/ACM_PMS/PMS/ACM/SCWORKSHOPS25/253/0b09762d-8e84-11f0-957d-16ffd757ba29/OUT/scworkshops25-253.html)

--- 

### Bibtex

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

```latex
@article{dorier2025toward,
  author = {Dorier, Matthieu and Gueroudji, Amal and Hayot-Sasson, Valerie and Nguyen, Hai and Ockerman, Seth and Souza, Renan and Bicer, Tekin and Pan, Haochen and Carns, Philip and Chard, Kyle and others},
  doi = {10.3389/fhpcp.2025.1638203},
  journal = {Frontiers in High Performance Computing},
  keyword = {HPC, I/O, Streaming, Mochi, Mofka, Kafka, Redpanda},
  link = {https://www.frontiersin.org/journals/high-performance-computing/articles/10.3389/fhpcp.2025.1638203/abstract},
  publisher = {Frontiers in High Performance Computing},
  title = {Toward a Persistent Event-Streaming System for High-Performance Computing Applications},
  volume = {3},
  year = {2025}
}
```

```latex
@inproceedings{rosendo2025ai,
  address = {St Louis, MO, USA},
  author = {Rosendo, Daniel and DeWitt, Stephen and Souza, Renan and Austria, Phillipe and Ghosal, Tirthankar and McDonnell, Marshall and Miller, Ross and Skluzacek, Tyler J and Haley, James and Turcksin, Bruno and others},
  booktitle = {Extreme-Scale Experiment-in-the-Loop Computing ({XLOOP}) co-located with the {ACM}/{IEEE} International Conference for High Performance Computing, Networking, Storage, and Analysis ({SC})},
  pdf = {https://rafaelsilva.com/files/publications/rosendo2025xloop.pdf},
  publisher = {ACM},
  title = {AI Agents for Enabling Autonomous Experiments at ORNL’s HPC and Manufacturing User Facilities},
  year = {2025}
}
```
