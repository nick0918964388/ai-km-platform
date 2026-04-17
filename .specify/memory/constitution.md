<!--
  Sync Impact Report:
  Version: 1.0.0 (INITIAL)
  Modified Principles: N/A (initial creation)
  Added Sections: All (initial creation)
  Removed Sections: N/A
  Templates Requiring Updates:
    ✅ plan-template.md - No changes needed (constitution check already present)
    ✅ spec-template.md - No changes needed (requirements section compatible)
    ✅ tasks-template.md - No changes needed (task structure compatible)
  Follow-up TODOs: None
-->

# AI Knowledge Management Platform Constitution

## Core Principles

### I. TypeScript Strict Mode

All frontend code MUST use TypeScript in strict mode. Type safety is non-negotiable:

- `strict: true` in tsconfig.json
- No `any` types without explicit justification
- All component props must be typed
- All API responses must have defined interfaces
- Zustand stores must have typed state and actions

**Rationale**: Type safety prevents runtime errors, improves code maintainability, and enables better IDE support for large-scale React applications.

### II. React Best Practices

React code MUST follow modern patterns and conventions:

- Functional components with hooks (no class components)
- Custom hooks for reusable logic
- Proper dependency arrays in useEffect/useMemo/useCallback
- Component composition over prop drilling (use Zustand for global state)
- Server components by default in Next.js (use 'use client' only when needed)

**Rationale**: Modern React patterns improve code reusability, performance, and maintainability. Server components reduce client bundle size.

### III. FastAPI Standard Architecture

Backend code MUST follow FastAPI best practices:

- Routers for endpoint organization (`app/routers/`)
- Pydantic models for request/response validation
- Service layer for business logic (`app/services/`)
- Repository pattern for data access when appropriate
- Async/await for I/O operations
- Dependency injection for shared resources

**Rationale**: Separation of concerns improves testability and maintainability. FastAPI's async nature maximizes performance.

### IV. Qdrant Integration Standards

Vector database operations MUST follow these guidelines:

- Use Qdrant Python client (not HTTP API directly)
- Define collection schemas explicitly
- Use appropriate distance metrics (Cosine for text embeddings)
- Implement proper error handling for connection failures
- Use filters for metadata-based queries
- Batch operations when possible for performance

**Rationale**: Proper Qdrant usage ensures consistent vector search performance and reliability.

### V. Component Library Consistency

UI components MUST adhere to the chosen design system:

- IBM Carbon Design components are the primary UI library
- Tailwind CSS v4 for custom styling and layout
- Custom components must match Carbon Design aesthetics
- Responsive design required (mobile-first approach)
- Accessibility standards (WCAG 2.1 AA minimum)

**Rationale**: Consistent UI patterns improve user experience and reduce development time. Carbon provides enterprise-grade components.

### VI. API Contract Consistency

All API endpoints MUST maintain strict contracts:

- OpenAPI/Swagger documentation required
- RESTful conventions (proper HTTP methods and status codes)
- Consistent error response format (FastAPI HTTPException)
- Versioning for breaking changes (e.g., `/v1/`, `/v2/`)
- Request/response validation via Pydantic models

**Rationale**: Clear contracts enable frontend-backend decoupling and prevent integration issues.

## Testing Requirements

### Unit Testing Standards

- **Frontend**: Jest + React Testing Library for component tests
- **Backend**: Pytest for service and utility tests
- **Coverage**: Minimum 70% coverage for critical business logic
- **Mocking**: Use MSW for API mocking in frontend tests

### Integration Testing Standards

- **API Tests**: Test complete request-response cycles
- **Database Tests**: Test with real Qdrant/PostgreSQL instances (test containers)
- **E2E Tests**: Playwright for critical user flows (optional, based on feature spec)

### Test-Driven Development (TDD)

TDD is OPTIONAL unless explicitly specified in feature requirements:

- If tests are requested in the feature spec, write tests before implementation
- Follow Red-Green-Refactor cycle when TDD is applied
- Tests must fail before implementation proves correctness

## Performance Standards

### Frontend Performance

- First Contentful Paint < 1.5s
- Time to Interactive < 3s
- Lighthouse score > 90
- Code splitting for routes
- Image optimization (Next.js Image component)

### Backend Performance

- API response time < 200ms (p95) for non-LLM endpoints
- Vector search < 100ms for typical queries
- Connection pooling for databases
- Redis caching for expensive operations

## Security Standards

### Authentication & Authorization

- JWT tokens for API authentication (when applicable)
- Secure password hashing (bcrypt/argon2)
- CORS configuration restrictive by default
- Environment variables for secrets (never commit secrets)

### Data Protection

- Input validation on all endpoints (Pydantic)
- SQL injection prevention (use ORMs/parameterized queries)
- XSS prevention (React escapes by default, be careful with dangerouslySetInnerHTML)
- HTTPS in production

## Development Workflow

### Code Quality Gates

- TypeScript compilation must pass (no errors)
- Linting must pass (ESLint for frontend, Ruff for backend)
- Formatting enforced (Prettier for frontend, Black/Ruff for backend)
- All tests must pass before PR merge

### Git Workflow

- Feature branches from `main` (`###-feature-name` naming)
- Conventional commits encouraged
- PR required for main branch changes
- Code review by at least one team member

### Documentation Requirements

- README.md for project setup instructions
- API documentation via Swagger (auto-generated)
- Component documentation for complex UI components (Storybook optional)
- Feature documentation in `/specs/` directory (SpecKit workflow)

## Governance

### Amendment Process

1. Propose amendment with rationale
2. Discuss impact on existing codebase
3. Document migration path if breaking
4. Update constitution version (semantic versioning)
5. Update dependent templates and documentation

### Compliance Verification

- All PRs must reference applicable constitution principles
- Architecture decisions must justify deviations from constitution
- Quarterly review of constitution relevance
- Use CLAUDE.md for runtime development guidance (auto-generated from feature plans)

### Complexity Justification

Any deviation from these principles MUST be justified in the implementation plan's "Complexity Tracking" section:

- Why the deviation is necessary
- What simpler alternatives were considered
- Why those alternatives were rejected

**Version**: 1.0.0 | **Ratified**: 2026-02-03 | **Last Amended**: 2026-02-03
