import { renderHook } from '@testing-library/react';

import { useVariableValue } from '../../js/shared/interactivity';
import { DerivedDataVariable, DerivedVariable, SingleVariable } from '../../js/types';
import { Wrapper, server } from './utils';

describe('useVariableValue', () => {
    beforeEach(() => server.listen());
    afterEach(() => server.resetHandlers());
    afterAll(() => server.close());

    it('should return a callback that creates the correct structure', () => {
        const variable: SingleVariable<number> = {
            __typename: 'Variable',
            default: 5,
            nested: [],
            uid: 'single',
        };

        const nestedDerivedVariable: DerivedVariable = {
            __typename: 'DerivedVariable',
            deps: [variable],
            nested: [],
            uid: 'nested-derived',
            variables: [variable],
        };

        const variableNotInDeps: SingleVariable<number> = {
            __typename: 'Variable',
            default: 1,
            nested: [],
            uid: 'single-number',
        };

        const derivedVariable: DerivedVariable = {
            __typename: 'DerivedVariable',
            deps: [nestedDerivedVariable, variableNotInDeps],
            nested: [],
            uid: 'derived',
            variables: [nestedDerivedVariable, variableNotInDeps],
        };

        const { result } = renderHook(() => useVariableValue(derivedVariable), { wrapper: Wrapper });

        expect(result.current).toBeInstanceOf(Function);

        const resolved = result.current();
        expect(resolved).toEqual({
            deps: [0, 1],
            type: 'derived',
            uid: derivedVariable.uid,
            values: [
                {
                    deps: [0],
                    type: 'derived',
                    uid: nestedDerivedVariable.uid,
                    values: [variable.default],
                },
                variableNotInDeps.default,
            ],
        });
    });

    it('should return a promise for the derived variable if shouldFetchVariable is set to true', async () => {
        const variable: SingleVariable<number> = {
            __typename: 'Variable',
            default: 5,
            nested: [],
            uid: 'single',
        };

        const nestedDerivedVariable: DerivedVariable = {
            __typename: 'DerivedVariable',
            deps: [variable],
            nested: [],
            uid: 'nested-derived',
            variables: [variable],
        };

        const variableNotInDeps: SingleVariable<number> = {
            __typename: 'Variable',
            default: 1,
            nested: [],
            uid: 'single-number',
        };

        const derivedVariable: DerivedVariable = {
            __typename: 'DerivedVariable',
            deps: [nestedDerivedVariable, variableNotInDeps],
            nested: [],
            uid: 'derived',
            variables: [nestedDerivedVariable, variableNotInDeps],
        };

        const { result } = renderHook(() => useVariableValue(derivedVariable, true), { wrapper: Wrapper });

        expect(result.current).toBeInstanceOf(Function);

        const resolved = result.current() as Promise<any>;
        expect(typeof resolved === 'object' && typeof resolved.then === 'function').toBe(true);
        const res = await resolved;
        expect(res).toEqual({
            force: false,
            is_data_variable: false,
            values: {
                data: [
                    {
                        force: false,
                        type: 'derived',
                        uid: 'nested-derived',
                        values: [
                            {
                                __ref: 'Variable:single',
                            },
                        ],
                    },
                    {
                        __ref: 'Variable:single-number',
                    },
                ],
                lookup: {
                    'Variable:single': 5,
                    'Variable:single-number': 1,
                },
            },
            ws_channel: 'uid',
        });
    });

    it('should return a promise for derived data variable if shouldFetchVariable is true', async () => {
        const variable: SingleVariable<number> = {
            __typename: 'Variable',
            default: 5,
            nested: [],
            uid: 'single',
        };

        const derivedDataVariable: DerivedDataVariable = {
            __typename: 'DerivedDataVariable',
            deps: [variable],
            filters: {
                column: 'col1',
                value: 'val1',
            },
            uid: 'derived',
            variables: [variable],
        };

        const { result } = renderHook(() => useVariableValue(derivedDataVariable, true), { wrapper: Wrapper });

        expect(result.current).toBeInstanceOf(Function);

        const resolved = result.current() as Promise<any>;
        expect(typeof resolved === 'object' && typeof resolved.then === 'function').toBe(true);
        const res = await resolved;
        expect(res).toMatchObject([
            { col1: 1, col2: 6, col3: 'a', col4: 'f' },
            { col1: 2, col2: 5, col3: 'b', col4: 'e' },
            {
                cache_key: '{"data":[{"__ref":"Variable:single"}],"lookup":{"Variable:single":5}}', // mock cache key returned from DV endpoint, stringified values
                filters: { column: 'col1', value: 'val1' }, // filters are sent correctly
                ws_channel: 'uid', // mock ms_channel passed through
            },
        ]);
    });

    it('should resolve a derived data variable if shouldFetchVariable is false', () => {
        const variable: SingleVariable<number> = {
            __typename: 'Variable',
            default: 5,
            nested: [],
            uid: 'single',
        };

        const derivedDataVariable: DerivedDataVariable = {
            __typename: 'DerivedDataVariable',
            deps: [variable],
            filters: {
                column: 'col1',
                value: 'val1',
            },
            uid: 'derived',
            variables: [variable],
        };

        const { result } = renderHook(() => useVariableValue(derivedDataVariable, false), { wrapper: Wrapper });

        expect(result.current()).toEqual({
            deps: [0],
            filters: { column: 'col1', value: 'val1' },
            type: 'derived-data',
            uid: 'derived',
            values: [5],
        });
    });
});
