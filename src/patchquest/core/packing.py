"""Deterministically place indivisible blobs in explicitly owned intervals.

This allocator does not discover free space or establish resource ownership.
Callers supply verified half-open intervals and enforce hardware constraints.
"""


def pack_blobs(blobs, intervals, search_limit=100000):
    """Return name -> start without splitting blobs, with bounded backtracking.

    Sort largest blobs first, then prefer the smallest available interval.
    Equivalent failed capacity states are memoized. Exhaustion, invalid input
    and a search-budget limit fail explicitly; input objects are not modified.
    """
    if not isinstance(search_limit,int) or search_limit<1:
        raise ValueError('Search limit must be a positive integer')
    spaces=sorted(tuple(pair) for pair in intervals)
    if any(len(pair)!=2 or any(not isinstance(n,int) for n in pair) or not 0<=pair[0]<pair[1] for pair in spaces):
        raise ValueError('Invalid owned interval')
    if any(left[1]>right[0] for left,right in zip(spaces,spaces[1:])):
        raise ValueError('Overlapping owned intervals')
    if any(not isinstance(name,str) or not isinstance(data,bytes) or not data for name,data in blobs.items()):
        raise ValueError('Named blobs must be nonempty bytes')
    order=sorted(blobs,key=lambda name:(-len(blobs[name]),name))
    remaining=[0]*(len(order)+1)
    for i in range(len(order)-1,-1,-1):remaining[i]=remaining[i+1]+len(blobs[order[i]])
    result={};failed=set();visited=0

    def visit(index,free):
        nonlocal visited
        if index==len(order):return True
        key=(index,tuple(sorted(end-start for start,end in free)))
        if key in failed:return False
        if sum(end-start for start,end in free)<remaining[index]:return False
        visited+=1
        if visited>search_limit:raise ValueError('Packing search limit exceeded')
        name=order[index];size=len(blobs[name]);tried=set()
        for j in sorted(range(len(free)),key=lambda j:(free[j][1]-free[j][0],free[j][0])):
            start,end=free[j];capacity=end-start
            if capacity<size or capacity in tried:continue
            tried.add(capacity);result[name]=start
            rest=list(free);rest[j]=(start+size,end)
            if visit(index+1,rest):return True
        result.pop(name,None);failed.add(key);return False

    if not visit(0,spaces):raise ValueError('Insufficient owned capacity for indivisible blobs')
    return result
