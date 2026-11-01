# 🎓 EduPilot AI

### Your AI-Powered Companion for the Entire Scholarship Journey

**Discover opportunities. Understand your eligibility. Prepare applications. Never miss important scholarship updates.**

EduPilot AI is an intelligent, AI-powered scholarship assistance platform designed to simplify the scholarship journey for students across India. It brings scholarship discovery, personalised eligibility assessment, document management, application assistance and scholarship tracking together in one place.

Instead of spending hours searching multiple websites, interpreting complicated eligibility conditions and repeatedly checking application deadlines, students can use EduPilot AI to get personalised assistance throughout their scholarship journey.

---

## 🌟 The Problem

Thousands of students miss valuable scholarship opportunities every year—not necessarily because they are ineligible, but because finding and applying for scholarships can be complicated.

Students often face challenges such as:

* **Scattered Information:** Scholarship information is distributed across government portals, universities, private organisations and different scholarship platforms.
* **Eligibility Confusion:** Understanding complicated eligibility criteria involving academic performance, family income, education level, category and institution can be difficult.
* **Document Management:** Students repeatedly upload and organise documents for different applications.
* **Complex Applications:** Filling lengthy application forms and understanding application instructions can be confusing.
* **Missed Deadlines:** Students may forget application deadlines, correction windows and renewal dates.
* **Lack of Follow-up:** Tracking application progress, responding to correction requests and checking payment updates can require repeated manual effort.
* **Unreliable Information:** Outdated announcements and suspicious scholarship links can put students at risk.

EduPilot AI aims to address these challenges through a unified, student-friendly and proactive scholarship assistance system.

---

## 💡 Our Solution

EduPilot AI acts as a personalised scholarship assistant that supports students from discovering an opportunity to managing their scholarship applications and renewals.

The platform is designed for students across different educational backgrounds, including:

* School education
* Intermediate (MPC, BiPC, Commerce and Arts)
* Diploma programmes
* Undergraduate programmes
* Postgraduate programmes
* Doctoral and research programmes
* Professional and vocational courses
* Other eligible educational programmes

Whether a student is pursuing engineering, medicine, commerce, arts, law, management, science or another course, scholarship recommendations are based on the actual eligibility conditions of each opportunity.

---

## ✨ Key Features

### 1. 🤖 AI-Powered Student Onboarding

* Conversational onboarding instead of complicated registration forms.
* Collects relevant academic, personal and financial information through guided questions.
* Builds a structured student profile from the provided information.
* Identifies missing or unclear profile details.
* Allows students to skip information that is not currently required and complete it later.
* Supports profile updates as students progress through their education.

### 2. 🔍 Intelligent Scholarship Discovery

* Discover scholarships from different providers and categories.
* Search, filter, compare and save scholarship opportunities.
* Receive personalised recommendations based on student profiles.
* Explore scholarship benefits, eligibility conditions, required documents and deadlines.
* Access official application links and available source information.
* View verification status and last-verified dates where available.

### 3. 🎯 Explainable Eligibility Assessment

* Compare student information against scholarship eligibility requirements.
* Evaluate relevant conditions such as education level, course, academic performance, family income and institution.
* Identify missing information that prevents a reliable assessment.
* Explain why a student may or may not satisfy individual eligibility conditions.
* Distinguish between likely eligible, possibly eligible, not eligible and requiring more information.

**The goal is not simply to display a matching percentage, but to help students understand the reasons behind an eligibility assessment.**

### 4. 📁 Smart Document Vault

* Upload and organise academic and personal documents.
* Store and reuse documents for different scholarship applications.
* Extract relevant information from uploaded documents where supported.
* Allow students to review and correct extracted information.
* Identify missing, unreadable, expired or incomplete documents.
* Check document readiness against individual scholarship requirements.

Automated document checks indicate readiness and consistency; they do not certify document authenticity.

### 5. 📝 AI-Assisted Application Preparation

* Map available profile information to application fields.
* Reuse previously provided information to reduce repetitive data entry.
* Generate suggested answers for supported application fields.
* Allow students to review, edit and approve prepared information.
* Check document readiness before application completion.
* Provide guidance for filling application forms on supported portals.

Where portal automation is unavailable or restricted, students receive instructions to complete the necessary steps manually.

### 6. 📊 Application Tracking

* Maintain a centralised view of scholarship applications.
* Track application statuses and available acknowledgements.
* Organise pending actions and correction requests.
* Record important application-related activities.
* Provide guidance for understanding rejection reasons and grievance procedures.
* Monitor payment updates when reliable official information is available.

### 7. 🔔 Proactive Notifications and Reminders

* Notify students about relevant scholarship opportunities.
* Provide reminders for approaching application deadlines.
* Highlight correction windows and renewal dates.
* Share available application status and payment updates.
* Support email and other configured notification channels.
* Allow students to manage notification preferences and quiet hours.

### 8. 💬 AI Scholarship Assistant

Students can interact with the AI Assistant using natural language to:

* Ask questions about scholarships.
* Understand complicated eligibility conditions.
* Find missing profile information.
* Understand document requirements.
* Get application preparation guidance.
* Clarify application procedures.
* Receive assistance with renewals and correction requests.

The assistant is designed to provide explanations grounded in available scholarship information rather than making unsupported assumptions.

### 9. 🛡️ Restricted Administration

The platform includes an administrative interface for authorised internal users to:

* Review uncertain or conflicting scholarship information.
* Investigate outdated or suspicious scholarship records.
* Monitor automated operations.
* Handle escalated support cases.
* Review system activity and operational issues.
* Manage authorised administrative configurations.

Sensitive student information is restricted according to assigned permissions.

---

## 🔄 How EduPilot AI Works

The platform follows an end-to-end scholarship assistance workflow:

```text
        STUDENT REGISTRATION
                 |
                 v
       CONVERSATIONAL ONBOARDING
                 |
                 v
        STUDENT PROFILE CREATION
                 |
                 v
        DOCUMENT VAULT MANAGEMENT
                 |
                 v
       SCHOLARSHIP DISCOVERY
                 |
                 v
       PERSONALIZED RECOMMENDATIONS
                 |
                 v
       ELIGIBILITY ASSESSMENT
                 |
                 v
       DOCUMENT READINESS CHECK
                 |
                 v
       APPLICATION PREPARATION
                 |
                 v
       STUDENT REVIEW AND APPROVAL
                 |
                 v
       SUPPORTED APPLICATION COMPLETION
                 |
                 v
       APPLICATION TRACKING
                 |
                 v
       PROACTIVE NOTIFICATIONS
                 |
                 v
       CORRECTIONS, PAYMENTS
          AND RENEWALS
```

---

## 🧠 AI and Technology

EduPilot AI combines a web application backend with AI-assisted workflows to provide personalised scholarship support.

### Current Development Stack

| Component               | Technology            |
| ----------------------- | --------------------- |
| Backend                 | Python                |
| Backend Framework       | FastAPI               |
| Frontend                | Web-based interface   |
| Database                | SQLite                |
| AI Integration          | Google Gemini API     |
| Local AI / Fallback     | Ollama with Llama 3   |
| API Communication       | REST / JSON HTTP APIs |
| Email Notifications     | SMTP                  |
| Development Environment | Visual Studio Code    |
| Version Control         | Git and GitHub        |

*The table describes the current development setup. Individual integrations and capabilities may vary depending on configuration.*

### AI Integration

The platform uses AI to assist with:

* Conversational student onboarding.
* Understanding scholarship requirements.
* Personalised scholarship assistance.
* Eligibility explanations.
* Document information extraction.
* Application preparation.
* Natural-language scholarship queries.

The system is designed to support alternative AI execution paths where configured, including local model inference through Ollama.

---

## 🔐 Security, Privacy and Responsible AI

Student profiles and scholarship documents may contain sensitive personal and financial information. EduPilot AI is designed with privacy and user control in mind.

Important safeguards include:

* API keys and credentials must be stored in backend environment configuration.
* Actual `.env` files must never be committed to GitHub.
* Student information must be protected through appropriate access controls.
* Students should be able to review and correct AI-generated information.
* Automated eligibility assessments must not be presented as guaranteed scholarship approval.
* Document checks must not be represented as authenticity certification.
* Final scholarship application submission requires explicit student approval.
* OTP, CAPTCHA, biometric verification, payments and mandatory declarations remain under student control.
* Uncertain information should be flagged or escalated instead of being treated as verified.

---

## 🛠️ Getting Started

Follow these steps to run the project locally.

### Prerequisites

Make sure you have installed:

* Python 3.10 or later
* Git
* Visual Studio Code (recommended)
* A supported AI provider configuration, if you want to use external AI services
* Ollama, if you want to run a supported local model

### 1. Clone the Repository

```bash
git clone https://github.com/dgeyakeerthi/EduPilot-AI.git
```

### 2. Navigate to the Project

```bash
cd EduPilot-AI
```

### 3. Create a Virtual Environment

```bash
python -m venv venv
```

### 4. Activate the Virtual Environment

**Windows PowerShell:**

```powershell
.\venv\Scripts\Activate.ps1
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Create a `.env` file in the project root.

If an `.env.example` file is provided, copy it:

```powershell
Copy-Item .env.example .env
```

Add the required configuration values using the variable names documented in `.env.example`.

**Important:** Never share your actual API keys, email credentials or other secrets.

### 7. Start the Backend

From the project root, run:

```bash
python -m uvicorn backend.main:app --reload
```

The backend should be available at:

```text
http://127.0.0.1:8000
```

If enabled, interactive API documentation can be accessed at:

```text
http://127.0.0.1:8000/docs
```

Follow the project's frontend instructions if the frontend is configured to run separately.

---

## 📂 Project Structure

The project is organised around frontend and backend responsibilities.

```text
EduPilot-AI/
│
├── backend/
│   ├── main.py
│   └── ...
│
├── frontend/
│   └── ...
│
├── tests/
│   └── ...
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── ...
```

*This is a simplified overview. Refer to the repository for the actual implementation and additional modules.*

---

## 🧪 Development and Testing

The project is being developed iteratively, with a focus on:

* Backend API functionality.
* Student registration and profile workflows.
* Scholarship discovery and eligibility processing.
* Document handling.
* AI integration and fallback behaviour.
* Application workflow validation.
* Notification delivery.
* Role-based access and security.

Run the relevant project tests using the test instructions provided with the implementation.

---

## 🚧 Current Development Status

EduPilot AI is an actively developed project.

The implementation includes a working backend development environment, AI integration experiments, scholarship-related workflows and an administrative interface.

Some capabilities are still under development or depend on external integrations, configuration and portal support.

In particular:

* Scholarship information may include demonstration records while reliable source integrations are being developed.
* Automated discovery from external scholarship websites can be limited by their access policies and technical restrictions.
* Eligibility assessments depend on the accuracy and completeness of available scholarship information.
* Application automation is limited to supported workflows and portals.
* Payment and application status updates are shown only when reliable information is available.

The project does not claim that every scholarship provider is integrated or that applications can be submitted automatically to every external portal.

---

## 🎯 Vision

Our vision is to make scholarship opportunities easier to discover and access by reducing the complexity involved in finding, understanding and managing applications.

EduPilot AI aims to move beyond being just another scholarship listing website by providing a personalised assistant that supports students throughout the entire scholarship lifecycle.

**One platform. One personalised assistant. A simpler scholarship journey.**

---

## 🤝 Contributing

Contributions, suggestions and feedback are welcome!

If you would like to contribute:

1. Fork this repository.
2. Create a new feature branch.
3. Make your changes.
4. Test your implementation.
5. Submit a pull request describing your contribution.

Please avoid committing API keys, passwords, personal documents, database files containing private information or other sensitive data.

---

## 👩‍💻 Project

**EduPilot AI**

An AI-powered scholarship assistance platform for students across India.

**GitHub:** https://github.com/dgeyakeerthi/EduPilot-AI

---

*Making scholarship discovery and application assistance simpler, smarter and more accessible.*
