# Frontend

This is a simple frontend template built with React, Vite, and TypeScript.

## Tech Stack

- **Framework**: [React 19](https://react.dev/)
- **Build Tool**: [Vite](https://vitejs.dev/)
- **Language**: [TypeScript](https://www.typescriptlang.org/)
- **Linting**: [ESLint](https://eslint.org/)

## Getting Started

### Prerequisites

Make sure you have a recent version of [Node.js](https://nodejs.org/) installed on your machine.

### Installation & Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repository-url>
    cd frontend
    ```

2.  **Install dependencies:**

    ```bash
    npm install
    ```

3.  **Run the development server:**
    ```bash
    npm run dev
    ```
    The application will be available at `http://localhost:5173`.

## Available Scripts

In the project directory, you can run:

- `npm run dev`
  Runs the app in development mode with hot-reloading.

- `npm run build`
  Builds the app for production. It type-checks the files and bundles them in the `dist` folder.

- `npm run lint`
  Lints the code using ESLint to check for code quality and style issues.

- `npm run preview`
  Serves the production build locally to preview your final app.

## Project Structure

- `src/components/`: Contains reusable React components.
- `src/apiClient.ts`: A starting point for your API communication logic.
- `public/`: Holds static assets like `favicon.ico` that are served directly.
- `App.tsx`: The main application component.
